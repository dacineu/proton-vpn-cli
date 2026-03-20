"""Remote adapter runner: handles JSON-RPC for adapter subprocesses.

This module provides a main loop that reads JSON messages from stdin,
dispatches them to a VPNAdapter instance, and writes responses to stdout.
"""

import asyncio
import json
import logging
import sys
from typing import Any, Dict, List, Optional, Tuple, Type

from .base import VPNAdapter
from ..models.config import ConnectionConfig
from ..models.tunnel import Tunnel
from ..models.status import TunnelStatus
from ..models.exceptions import TunnelError, AdapterError
from libvpnmanager.sessions import proton, psiphon, wireguard, dummy

logger = logging.getLogger(__name__)

# Mapping from adapter type to session class
SESSION_CLASSES = {
    "proton": proton.ProtonSession,
    "psiphon": psiphon.PsiphonSession,
    "wireguard": wireguard.WireGuardSession,
    "dummy": dummy.DummySession,
}


class RemoteAdapterServer:
    """Handles RPC for a single adapter subprocess."""

    def __init__(self, adapter_class: Type[VPNAdapter], adapter_type: str):
        self.adapter_class = adapter_class
        self.adapter_type = adapter_type
        self.adapter: Optional[VPNAdapter] = None
        self._msg_id_counter = 0
        self._pending: Dict[int, Tuple[asyncio.Future, Optional[callable]]] = {}

    def _next_msg_id(self) -> int:
        self._msg_id_counter += 1
        return self._msg_id_counter

    async def _send_message(self, payload: Dict[str, Any]):
        """Send a JSON message to stdout."""
        try:
            line = json.dumps(payload) + "\n"
            sys.stdout.write(line)
            sys.stdout.flush()
        except Exception as e:
            logger.error(f"Failed to send message: {e}")
            raise

    async def _handle_message(self, msg: Dict[str, Any]):
        """Process an incoming RPC message."""
        msg_id = msg.get("msg_id")
        method = msg.get("method")
        params = msg.get("params", {})

        if msg_id is None:
            logger.warning("Message missing msg_id, ignoring")
            return

        # Special methods: initialize, shutdown
        if method == "initialize":
            await self._handle_initialize(msg_id, params)
            return
        elif method == "shutdown":
            await self._handle_shutdown(msg_id)
            return

        # All other methods require adapter to be initialized
        if self.adapter is None:
            await self._send_error(msg_id, "Adapter not initialized")
            return

        try:
            # Dispatch to adapter method
            result = await self._dispatch_method(method, params, msg_id)
            if result is not None:
                await self._send_result(msg_id, result)
            else:
                await self._send_result(msg_id, {})
        except Exception as e:
            logger.exception(f"Error handling method {method}")
            await self._send_error(msg_id, str(e))

    async def _handle_initialize(self, msg_id: int, params: Dict[str, Any]):
        """Handle initialization: construct the adapter with session data."""
        session_data = params.get("session")
        if not session_data:
            await self._send_error(msg_id, "Missing session data")
            return

        # Get the correct session class based on adapter_type (which we know)
        session_cls = SESSION_CLASSES.get(self.adapter_type)
        if session_cls is None:
            await self._send_error(msg_id, f"Unknown adapter type: {self.adapter_type}")
            return

        try:
            session = session_cls.from_dict(session_data)
        except Exception as e:
            await self._send_error(msg_id, f"Failed to reconstruct session: {e}")
            return

        try:
            self.adapter = self.adapter_class(session)
            await self._send_result(msg_id, {})
        except Exception as e:
            await self._send_error(msg_id, f"Failed to instantiate adapter: {e}")

    async def _handle_shutdown(self, msg_id: int):
        """Handle shutdown: cleanup adapter and exit."""
        if self.adapter:
            try:
                await self.adapter.cleanup()
            except Exception as e:
                logger.warning(f"Cleanup error: {e}")
        await self._send_result(msg_id, {})
        # Signal exit by raising SystemExit in the read loop
        raise SystemExit(0)

    async def _dispatch_method(self, method: str, params: Dict[str, Any], msg_id: int) -> Any:
        """Call the appropriate method on the adapter and return result."""
        # Resolve the method on the adapter
        try:
            func = getattr(self.adapter, method)
        except AttributeError:
            raise AdapterError(f"Unknown method: {method}")

        # For connect, pass config and progress callback
        if method == "connect":
            config_dict = params.get("config")
            if not config_dict:
                raise AdapterError("Missing config for connect")
            config = ConnectionConfig.from_dict(config_dict)

            # Create a progress callback that sends progress messages
            def progress_callback(message: str):
                # Send progress asynchronously (fire-and-forget)
                try:
                    prog_msg = {"msg_id": msg_id, "type": "progress", "message": message}
                    asyncio.create_task(self._send_message(prog_msg))
                except Exception as e:
                    logger.warning(f"Failed to send progress: {e}")

            return await func(config, progress_callback=progress_callback)

        # For methods that take a Tunnel argument
        elif method in ("disconnect", "get_status", "get_traffic_stats"):
            tunnel_dict = params.get("tunnel")
            if not tunnel_dict:
                raise AdapterError(f"Missing tunnel for {method}")
            tunnel = Tunnel.from_dict(tunnel_dict)
            return await func(tunnel)

        # For get_capabilities (no params)
        elif method == "get_capabilities":
            caps = await func()
            # Convert dataclass to dict
            if hasattr(caps, '__dataclass_fields__'):
                return caps.__dict__.copy()
            return caps

        # For list_tunnels (no params)
        elif method == "list_tunnels":
            tunnels = await func()
            # Convert list of Tunnel to list of dicts
            return [t.to_dict() for t in tunnels]

        # For cleanup (no params, no return)
        elif method == "cleanup":
            await func()
            return {}  # empty result

        # Other methods (if any) just pass params as kwargs?
        else:
            # Try generic call with **params
            return await func(**params)

    async def _send_result(self, msg_id: int, result: Any):
        payload = {"msg_id": msg_id, "type": "result", "result": result}
        await self._send_message(payload)

    async def _send_error(self, msg_id: int, error: str):
        payload = {"msg_id": msg_id, "type": "error", "error": error}
        await self._send_message(payload)

    async def run(self):
        """Main loop: read messages from stdin and dispatch."""
        loop = asyncio.get_event_loop()
        logger = logging.getLogger(__name__)
        while True:
            # Read line from stdin in a thread to avoid blocking
            line = await loop.run_in_executor(None, sys.stdin.readline)
            if not line:
                logger.info("EOF on stdin, exiting")
                break
            try:
                msg = json.loads(line)
                await self._handle_message(msg)
            except json.JSONDecodeError as e:
                logger.warning(f"Invalid JSON: {e}")
            except SystemExit:
                logger.info("Shutdown requested, exiting")
                break
            except Exception as e:
                logger.exception(f"Unexpected error processing message")


async def run_adapter(adapter_class: Type[VPNAdapter], adapter_type: str):
    """
    Entry point for running an adapter as a subprocess.

    Args:
        adapter_class: The VPNAdapter subclass to instantiate upon initialize.
        adapter_type: Adapter type string (e.g., "proton").
    """
    logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(name)s: %(message)s")
    server = RemoteAdapterServer(adapter_class, adapter_type)
    try:
        await server.run()
    except KeyboardInterrupt:
        logger.info("Interrupted")
    finally:
        if server.adapter:
            try:
                await server.adapter.cleanup()
            except Exception:
                pass
