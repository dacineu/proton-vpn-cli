"""Unix socket IPC transport.

Provides local inter-process communication via Unix domain sockets.
Works on Linux, macOS, BSD, and Windows 10+ (AF_UNIX).

Security: Socket file ownership and permissions control access.
Typical path: /run/protonvpn/manager.sock (Linux) or $XDG_RUNTIME_DIR/protonvpn/manager.sock
"""

import asyncio
import json
import os
import socket
from pathlib import Path
from typing import Any, Dict, Callable, Awaitable
from ..models.exceptions import VPNManagerError

from .transport import (
    IPCTransport, IPCServer, IPCClient, Message, MessageType, TransportConfig, IPCError, register_transport
)


class UnixSocketServer(IPCServer):
    """Unix socket IPC server."""

    DEFAULT_PATH = "/run/protonvpn/manager.sock"
    DEFAULT_UMASK = 0o077  # Socket readable/writable only by owner

    def __init__(self, manager: Any, config: TransportConfig):
        super().__init__(manager)
        self.config = config
        self.path = config.extra.get('socket_path', self.DEFAULT_PATH)
        self._server: Optional[asyncio.Server] = None
        self._clients: set[asyncio.StreamWriter] = set()

    async def start(self) -> None:
        """Start listening on Unix socket."""
        # Ensure parent directory exists
        sock_dir = Path(self.path).parent
        sock_dir.mkdir(parents=True, exist_ok=True)

        # Remove existing socket if stale
        try:
            os.unlink(self.path)
        except FileNotFoundError:
            pass
        except PermissionError:
            pass  # Might be owned by another user

        # Create socket with proper permissions
        sock = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
        sock.setblocking(False)

        # Set umask temporarily to create socket with 0600
        old_umask = os.umask(self.DEFAULT_UMASK)
        try:
            sock.bind(self.path)
        finally:
            os.umask(old_umask)

        # Set socket ownership if running as root (optional: chown to protonvpn user)
        # This would require knowing the user; skip for now.

        sock.listen(128)
        self._server = await asyncio.start_unix_server(
            client_connected_cb=self._handle_client,
            sock=sock
        )
        # Set permissions after server starts (in case they got modified)
        os.chmod(self.path, 0o600)

    async def stop(self) -> None:
        """Stop server and cleanup socket."""
        if self._server:
            self._server.close()
            await self._server.wait_closed()
            self._server = None

        # Close all clients
        for writer in self._clients:
            writer.close()
        await asyncio.gather(*[writer.wait_closed() for writer in self._clients if not writer.is_closing()])
        self._clients.clear()

        # Remove socket file
        try:
            os.unlink(self.path)
        except FileNotFoundError:
            pass

    async def emit_signal(self, signal: str, data: Dict[str, Any]) -> None:
        """Send a signal to all connected clients."""
        msg = Message.signal(signal, data)
        payload = self._serialize_message(msg)

        for writer in list(self._clients):
            try:
                writer.write(payload)
                await writer.drain()
            except Exception as e:
                # Dead client, remove
                self._clients.discard(writer)
                try:
                    writer.close()
                except:
                    pass

    async def _handle_client(
        self,
        reader: asyncio.StreamReader,
        writer: asyncio.StreamWriter
    ) -> None:
        """Handle a new client connection."""
        self._clients.add(writer)
        peer = writer.get_extra_info('peername')
        addr = getattr(peer, 'unix_socket', str(peer)) if peer else "unknown"

        try:
            while True:
                # Read message length (4-byte prefix)
                len_bytes = await reader.readexactly(4)
                if len(len_bytes) < 4:
                    break
                msg_len = int.from_bytes(len_bytes, 'big')
                if msg_len > 10 * 1024 * 1024:  # 10 MB max
                    raise IPCError("Message too large")

                # Read message body
                body = await reader.readexactly(msg_len)
                if not body:
                    break

                # Parse and handle
                try:
                    msg = self._deserialize_message(body)
                    response = await self.handle_request(msg)
                    resp_body = self._serialize_message(response)
                    writer.write(len(resp_body).to_bytes(4, 'big') + resp_body)
                    await writer.drain()
                except Exception as e:
                    error_msg = Message.error(msg.request_id if msg else 0, str(e))
                    writer.write(self._serialize_message(error_msg))
                    await writer.drain()
        except asyncio.IncompleteReadError:
            pass
        except Exception as e:
            print(f"UnixSocketServer: client {addr} error: {e}")
        finally:
            self._clients.discard(writer)
            writer.close()
            try:
                await writer.wait_closed()
            except:
                pass

    def _serialize_message(self, message: Message) -> bytes:
        """Encode message to bytes (JSON)."""
        data = message.to_dict()
        body = json.dumps(data).encode('utf-8')
        return len(body).to_bytes(4, 'big') + body

    def _deserialize_message(self, data: bytes) -> Message:
        """Decode message from bytes."""
        obj = json.loads(data.decode('utf-8'))
        return Message(
            msg_type=MessageType(obj['type']),
            method=obj.get('method'),
            params=obj.get('params', {}),
            request_id=obj.get('request_id'),
            result=obj.get('result'),
            error=obj.get('error'),
            signal_name=obj.get('signal'),
        )


class UnixSocketClient(IPCClient):
    """Unix socket IPC client."""

    def __init__(self, config: TransportConfig):
        super().__init__()
        self.config = config
        self.path = config.extra.get('socket_path', UnixSocketServer.DEFAULT_PATH)
        self._reader: Optional[asyncio.StreamReader] = None
        self._writer: Optional[asyncio.StreamWriter] = None
        self._pending_requests: Dict[int, asyncio.Future] = {}
        self._request_counter = 0
        self._listen_task: Optional[asyncio.Task] = None

    async def connect(self) -> None:
        """Connect to server."""
        self._reader, self._writer = await asyncio.open_unix_connection(self.path)
        self.connected = True

        # Start listener task for signals (if server pushes unsolicited messages)
        self._listen_task = asyncio.create_task(self._listen_loop())

    async def disconnect(self) -> None:
        """Disconnect from server."""
        if self._listen_task:
            self._listen_task.cancel()
            try:
                await self._listen_task
            except asyncio.CancelledError:
                pass
            self._listen_task = None

        if self._writer:
            self._writer.close()
            await self._writer.wait_closed()
            self._writer = None
            self._reader = None
        self.connected = False

        # Cancel any pending requests
        for future in self._pending_requests.values():
            if not future.done():
                future.set_exception(IPCError("Disconnected"))
        self._pending_requests.clear()

    async def call_method(
        self,
        method: str,
        params: Optional[Dict[str, Any]] = None
    ) -> Any:
        """Call a method synchronously (wait for response)."""
        if not self.connected:
            raise IPCError("Not connected")

        req_id = self._request_counter
        self._request_counter += 1
        future = asyncio.Future()
        self._pending_requests[req_id] = future

        msg = Message.request(method, params or {}, req_id)
        data = self._serialize_message(msg)
        self._writer.write(data)
        await self._writer.drain()

        try:
            response = await asyncio.wait_for(future, timeout=30.0)
            if response.error:
                raise IPCError(response.error)
            return response.result
        except asyncio.TimeoutError:
            self._pending_requests.pop(req_id, None)
            raise IPCError("Request timeout")

    async def subscribe_signal(
        self,
        signal: str,
        callback: Callable[[Dict[str, Any]], Awaitable[None]]
    ) -> None:
        """Subscribe to a signal. For Unix socket, we just call the callback from the listener."""
        # Could implement explicit Subscribe method to server, but for now just use generic
        # Assume server emits signals to all clients without registration
        pass  # Callback must be handled in _listen_loop

    async def _listen_loop(self) -> None:
        """Background task to read incoming messages (signals, responses)."""
        try:
            while True:
                if not self._reader:
                    break
                len_bytes = await self._reader.readexactly(4)
                if not len_bytes:
                    break
                msg_len = int.from_bytes(len_bytes, 'big')
                body = await self._reader.readexactly(msg_len)
                if not body:
                    break

                msg = self._deserialize_message(body)

                if msg.msg_type == MessageType.RESPONSE:
                    future = self._pending_requests.get(msg.request_id)
                    if future and not future.done():
                        future.set_result(msg)
                elif msg.msg_type == MessageType.SIGNAL:
                    # Call user-provided callback? For now, just log.
                    # In a real implementation, would have signal handlers registry.
                    pass
                elif msg.msg_type == MessageType.ERROR:
                    future = self._pending_requests.get(msg.request_id)
                    if future and not future.done():
                        future.set_exception(IPCError(msg.error or "Unknown error"))
        except (asyncio.IncompleteReadError, ConnectionError, BrokenPipeError):
            pass
        except Exception as e:
            print(f"UnixSocketClient listen error: {e}")

    def _serialize_message(self, message: Message) -> bytes:
        data = message.to_dict()
        body = json.dumps(data).encode('utf-8')
        return len(body).to_bytes(4, 'big') + body

    def _deserialize_message(self, data: bytes) -> Message:
        obj = json.loads(data.decode('utf-8'))
        return Message(
            msg_type=MessageType(obj['type']),
            method=obj.get('method'),
            params=obj.get('params', {}),
            request_id=obj.get('request_id'),
            result=obj.get('result'),
            error=obj.get('error'),
            signal_name=obj.get('signal'),
        )

# Register this transport (after class definitions)
register_transport('unix-socket', UnixSocketServer, UnixSocketClient)
