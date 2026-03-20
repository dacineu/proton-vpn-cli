"""Remote VPN adapter that communicates with a separate adapter process.

This adapter allows the multi-tunnel manager daemon to isolate VPN adapters
in separate processes for security, stability, and resource management.
"""

import asyncio
import json
import logging
import uuid
from typing import Any, Dict, Optional, Tuple

from .base import VPNAdapter, AdapterCapabilities
from ..models.tunnel import Tunnel
from ..models.config import ConnectionConfig
from ..models.exceptions import AdapterError, TunnelError


logger = logging.getLogger(__name__)


class RemoteVPNAdapter(VPNAdapter):
    """
    Adapter that proxies all calls to a separate process via stdin/stdout.

    The subprocess is expected to understand JSON-RPC messages and implement
    the same VPNAdapter interface.

    Lifecycle:
        - Instantiated by TunnelManager with a session object.
        - on first method call, spawns the subprocess and sends initialization.
        - All methods send JSON messages and wait for responses.
        - If the subprocess exits unexpectedly, adapter becomes non-functional.
        - cleanup() shuts down the subprocess.
    """

    # To be overridden in subclasses
    adapter_type: str = None   # e.g., "proton"
    executable: str = None     # path to the adapter executable

    def __init__(self, session):
        """
        Initialize remote adapter proxy.

        Args:
            session: Session object containing credentials/session data.
        """
        super().__init__()
        if self.adapter_type is None or self.executable is None:
            raise TypeError("RemoteVPNAdapter subclass must define adapter_type and executable")
        self.session = session
        self._process: Optional[asyncio.subprocess.Process] = None
        self._reader_task: Optional[asyncio.Task] = None
        self._msg_id_counter = 0
        self._pending: Dict[int, Tuple[asyncio.Future, Optional[callable]]] = {}
        self._lock = asyncio.Lock()
        self._closed = False
        self._last_error: Optional[Exception] = None

    async def _ensure_started(self):
        """Start the subprocess if not already running."""
        if self._closed:
            raise AdapterError("Adapter is closed")
        if self._process is not None and self._process.returncode is None:
            return  # already running

        async with self._lock:
            if self._process is not None:
                return

            try:
                logger.debug(f"Starting adapter subprocess: {self.executable}")
                self._process = await asyncio.create_subprocess_exec(
                    self.executable,
                    stdin=asyncio.subprocess.PIPE,
                    stdout=asyncio.subprocess.PIPE,
                    stderr=asyncio.subprocess.PIPE,
                )
                self._reader_task = asyncio.create_task(self._read_loop())

                # Send initialization with session data
                init_msg_id = self._next_msg_id()
                init_future: asyncio.Future = asyncio.Future()
                self._pending[init_msg_id] = (init_future, None)

                init_payload = {
                    "msg_id": init_msg_id,
                    "method": "initialize",
                    "params": {
                        "session": self.session.to_dict(),
                        "adapter_type": self.adapter_type,
                    }
                }
                await self._send_message(init_payload)

                # Wait for init to complete
                try:
                    await asyncio.wait_for(init_future, timeout=10.0)
                except asyncio.TimeoutError:
                    await self._terminate_process()
                    raise AdapterError("Adapter initialization timed out")
                except Exception as e:
                    await self._terminate_process()
                    raise AdapterError(f"Adapter initialization failed: {e}")

            except Exception as e:
                logger.error(f"Failed to start adapter process: {e}")
                if self._process:
                    await self._terminate_process()
                raise AdapterError(f"Could not start adapter: {e}")

    def _next_msg_id(self) -> int:
        """Generate a unique message ID."""
        self._msg_id_counter += 1
        return self._msg_id_counter

    async def _send_message(self, payload: Dict[str, Any]):
        """Send a JSON message to the subprocess."""
        if self._process is None or self._process.stdin is None:
            raise AdapterError("Adapter process not running")
        try:
            line = json.dumps(payload) + "\n"
            self._process.stdin.write(line.encode('utf-8'))
            await self._process.stdin.drain()
        except Exception as e:
            await self._terminate_process()
            raise AdapterError(f"Failed to send message to adapter: {e}")

    async def _read_loop(self):
        """Continuously read messages from subprocess stdout."""
        if self._process is None or self._process.stdout is None:
            return

        try:
            while True:
                line = await self._process.stdout.readline()
                if not line:
                    # EOF reached, process exited
                    break
                try:
                    msg = json.loads(line.decode('utf-8'))
                    await self._handle_message(msg)
                except json.JSONDecodeError as e:
                    logger.warning(f"Invalid JSON from adapter: {e}")
                except Exception as e:
                    logger.error(f"Error handling adapter message: {e}")
        except asyncio.CancelledError:
            logger.debug("Reader task cancelled")
        except Exception as e:
            logger.error(f"Reader task error: {e}")
        finally:
            # Mark process as no longer running
            was_closed = self._closed
            self._process = None
            # If the process exited unexpectedly (not during cleanup), fail all pending
            if not was_closed:
                await self._fail_all_pending("Adapter process terminated unexpectedly")

    async def _handle_message(self, msg: Dict[str, Any]):
        """Handle a message from the adapter process."""
        msg_id = msg.get("msg_id")
        msg_type = msg.get("type")  # "result" or "error" or "progress"

        if msg_id is None or msg_id not in self._pending:
            logger.warning(f"Unknown msg_id: {msg_id}")
            return

        future, progress_callback = self._pending[msg_id]

        if msg_type == "progress":
            # Progress update - invoke callback if present
            if progress_callback:
                try:
                    progress_msg = msg.get("message", "")
                    progress_callback(progress_msg)
                except Exception as e:
                    logger.warning(f"Progress callback error: {e}")
            # Do not remove from pending yet
        elif msg_type == "result":
            # Final result
            result = msg.get("result")
            if not future.done():
                future.set_result(result)
            self._pending.pop(msg_id, None)
        elif msg_type == "error":
            error_msg = msg.get("error", "Unknown error")
            if not future.done():
                future.set_exception(AdapterError(error_msg))
            self._pending.pop(msg_id, None)
        else:
            logger.warning(f"Unknown message type: {msg_type}")

    async def _fail_all_pending(self, error_msg: str):
        """Fail all pending futures due to process failure."""
        for msg_id, (future, _) in list(self._pending.items()):
            if not future.done():
                future.set_exception(AdapterError(error_msg))
            self._pending.pop(msg_id, None)

    async def _terminate_process(self):
        """Terminate the adapter subprocess."""
        if self._reader_task:
            self._reader_task.cancel()
            try:
                await self._reader_task
            except asyncio.CancelledError:
                pass
            self._reader_task = None

        if self._process:
            try:
                if self._process.returncode is None:
                    self._process.terminate()
                    try:
                        await asyncio.wait_for(self._process.wait(), timeout=5.0)
                    except asyncio.TimeoutError:
                        self._process.kill()
                        await self._process.wait()
            except Exception as e:
                logger.debug(f"Error terminating adapter process: {e}")
            finally:
                self._process = None

    @property
    def capabilities(self) -> AdapterCapabilities:
        """Return adapter capabilities (query from remote if needed, else default)."""
        # We could lazily load capabilities from the remote on first call.
        # For now, we assume generic capabilities; actual capabilities will be
        # fetched by the daemon via get_capabilities() on the adapter (which will be remote).
        # So this property should perform a remote call if possible? But capabilities is a sync property in base class.
        # That's problematic: we need to make it async in base.
        # For now, return a default, but we'll make it async later.
        # TODO: change base to async or cache from remote.
        return AdapterCapabilities(
            multi_tunnel=False,
            supports_protocols=[],
            max_tunnels=None,
            supports_per_app_routing=False,
            supports_kill_switch=False,
            supports_dns_isolation=False,
        )

    async def connect(
        self,
        config: ConnectionConfig,
        progress_callback: Optional[callable] = None,
    ) -> Tunnel:
        """
        Connect a VPN tunnel via the remote adapter process.

        Args:
            config: Connection configuration
            progress_callback: Optional callable for progress updates

        Returns:
            Tunnel object representing the connected tunnel
        """
        await self._ensure_started()

        msg_id = self._next_msg_id()
        future: asyncio.Future = asyncio.Future()
        self._pending[msg_id] = (future, progress_callback)

        payload = {
            "msg_id": msg_id,
            "method": "connect",
            "params": {
                "config": config.to_dict(),
            }
        }
        await self._send_message(payload)

        try:
            result_dict = await asyncio.wait_for(future, timeout=300.0)  # 5 min timeout for connect
        except asyncio.TimeoutError:
            raise AdapterError("Connection timed out")

        # Reconstruct Tunnel object
        tunnel = Tunnel.from_dict(result_dict)
        return tunnel

    async def disconnect(self, tunnel: Tunnel) -> None:
        """Disconnect a tunnel."""
        await self._ensure_started()

        msg_id = self._next_msg_id()
        future: asyncio.Future = asyncio.Future()
        self._pending[msg_id] = (future, None)

        payload = {
            "msg_id": msg_id,
            "method": "disconnect",
            "params": {
                "tunnel": tunnel.to_dict(),
            }
        }
        await self._send_message(payload)

        try:
            await future
        except asyncio.TimeoutError:
            raise AdapterError("Disconnect timed out")

    async def get_status(self, tunnel: Tunnel) -> TunnelStatus:
        """Get tunnel status."""
        await self._ensure_started()

        msg_id = self._next_msg_id()
        future: asyncio.Future = asyncio.Future()
        self._pending[msg_id] = (future, None)

        payload = {
            "msg_id": msg_id,
            "method": "get_status",
            "params": {
                "tunnel": tunnel.to_dict(),
            }
        }
        await self._send_message(payload)

        try:
            status_str = await asyncio.wait_for(future, timeout=30.0)
            return TunnelStatus(status_str)
        except asyncio.TimeoutError:
            raise AdapterError("get_status timed out")

    def list_tunnels(self) -> list[Tunnel]:
        """
        List all tunnels managed by this adapter.

        Note: This is a synchronous method but needs to communicate with subprocess.
        We'll run a temporary event loop to send the request.
        This is called only from cleanup or rarely, so blocking is acceptable.
        """
        # We cannot call async from sync easily; but this method might be called from sync context.
        # However, TunnelManager never calls it; it's only used maybe for diagnostics.
        # We'll implement a simple workaround by creating a new event loop in this thread.
        # Better: make this async in base? For now, raise NotImplemented to avoid using.
        raise NotImplementedError("list_tunnels not supported for remote adapter in sync mode")

    async def get_traffic_stats(self, tunnel: Tunnel) -> Tuple[int, int]:
        """Get traffic statistics."""
        await self._ensure_started()

        msg_id = self._next_msg_id()
        future: asyncio.Future = asyncio.Future()
        self._pending[msg_id] = (future, None)

        payload = {
            "msg_id": msg_id,
            "method": "get_traffic_stats",
            "params": {
                "tunnel": tunnel.to_dict(),
            }
        }
        await self._send_message(payload)

        try:
            result = await asyncio.wait_for(future, timeout=30.0)
            if isinstance(result, dict):
                return result.get("bytes_in", 0), result.get("bytes_out", 0)
            return tuple(result)  # assume (bytes_in, bytes_out)
        except asyncio.TimeoutError:
            raise AdapterError("get_traffic_stats timed out")

    async def get_capabilities(self) -> AdapterCapabilities:
        """Get adapter capabilities."""
        await self._ensure_started()

        msg_id = self._next_msg_id()
        future: asyncio.Future = asyncio.Future()
        self._pending[msg_id] = (future, None)

        payload = {
            "msg_id": msg_id,
            "method": "get_capabilities",
            "params": {}
        }
        await self._send_message(payload)

        try:
            caps_dict = await asyncio.wait_for(future, timeout=10.0)
            return AdapterCapabilities(**caps_dict)
        except asyncio.TimeoutError:
            raise AdapterError("get_capabilities timed out")

    async def cleanup(self) -> None:
        """Cleanup: shutdown the adapter subprocess."""
        if self._closed:
            return
        self._closed = True

        # If process is running, try graceful shutdown
        if self._process and self._process.returncode is None:
            try:
                # Ensure reader task is running
                if self._reader_task is None and self._process:
                    self._reader_task = asyncio.create_task(self._read_loop())

                msg_id = self._next_msg_id()
                future: asyncio.Future = asyncio.Future()
                self._pending[msg_id] = (future, None)
                payload = {
                    "msg_id": msg_id,
                    "method": "shutdown",
                    "params": {}
                }
                await self._send_message(payload)
                try:
                    await asyncio.wait_for(future, timeout=5.0)
                except asyncio.TimeoutError:
                    logger.warning("Adapter did not respond to shutdown, terminating")
            except Exception as e:
                logger.debug(f"Error sending shutdown: {e}")

        # Terminate process regardless
        await self._terminate_process()

        # Cancel reader task if still running
        if self._reader_task:
            self._reader_task.cancel()
            try:
                await self._reader_task
            except asyncio.CancelledError:
                pass
            self._reader_task = None

    # Optional: Additional methods for status registration, etc. Not implemented.


# Factory function to create a specific RemoteVPNAdapter subclass
def make_remote_adapter_class(adapter_type: str, executable: str):
    """
    Factory to create a RemoteVPNAdapter subclass for a given adapter type and executable.

    Returns a new class that has adapter_type and executable set.
    """
    class RemoteAdapterClass(RemoteVPNAdapter):
        _adapter_type = adapter_type
        _executable = executable

        def __init__(self, session):
            super().__init__(session)

    RemoteAdapterClass.__name__ = f"Remote{adapter_type.capitalize()}Adapter"
    RemoteAdapterClass.__qualname__ = f"Remote{adapter_type.capitalize()}Adapter"
    return RemoteAdapterClass
