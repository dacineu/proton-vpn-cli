"""Unix socket server for adapter processes (direct CLI connections)."""

import asyncio
import json
import logging
import os
from pathlib import Path
from typing import Any, Dict, Optional

from ..models.config import ConnectionConfig
from ..models.tunnel import Tunnel
from ..models.status import TunnelStatus

logger = logging.getLogger(__name__)


class UnixAdapterServer:
    """Server that accepts CLI connections on a Unix socket and dispatches to a VPNAdapter."""

    def __init__(self, adapter, control_socket: str, internal_socket: str):
        """
        Args:
            adapter: VPNAdapter instance
            control_socket: Path to Unix socket for CLI connections
            internal_socket: Path to MTM's internal resource socket
        """
        self.adapter = adapter
        self.control_socket = control_socket
        self.internal_socket = internal_socket
        self._server: Optional[asyncio.Server] = None
        self._adapter_lock = asyncio.Lock()  # serialize access to adapter

    async def run(self):
        """Start the server and run until cancelled."""
        socket_dir = Path(self.control_socket).parent
        socket_dir.mkdir(parents=True, exist_ok=True)
        try:
            Path(self.control_socket).unlink(missing_ok=True)
        except Exception as e:
            logger.warning(f"Could not remove old socket: {e}")

        self._server = await asyncio.start_unix_server(self._handle_client, self.control_socket)
        try:
            os.chmod(self.control_socket, 0o660)
        except Exception as e:
            logger.warning(f"Could not set socket perms: {e}")
        logger.info(f"Adapter server listening on {self.control_socket}")

        async with self._server:
            await self._server.wait_closed()

    async def stop(self):
        if self._server:
            self._server.close()
            await self._server.wait_closed()
            self._server = None
        try:
            Path(self.control_socket).unlink(missing_ok=True)
        except Exception:
            pass

    async def _call_internal(self, request: Dict[str, Any]) -> Dict[str, Any]:
        """Send a request to MTM's internal resource socket and get response."""
        try:
            reader, writer = await asyncio.open_unix_connection(self.internal_socket)
        except Exception as e:
            logger.error(f"Failed to connect to internal socket: {e}")
            return {"msg_type": "error", "error": f"Internal connection failed: {e}"}
        try:
            payload = json.dumps(request).encode('utf-8')
            writer.write(len(payload).to_bytes(4, 'big') + payload)
            await writer.drain()
            len_bytes = await reader.readexactly(4)
            resp_len = int.from_bytes(len_bytes, 'big')
            data = await reader.readexactly(resp_len)
            response = json.loads(data.decode('utf-8'))
            return response
        except asyncio.IncompleteReadError:
            return {"msg_type": "error", "error": "Incomplete response from internal socket"}
        except Exception as e:
            logger.error(f"Error during internal call: {e}")
            return {"msg_type": "error", "error": str(e)}
        finally:
            writer.close()
            await writer.wait_closed()

    async def _handle_client(self, reader: asyncio.StreamReader, writer: asyncio.StreamWriter):
        """Handle a client connection."""
        peer = writer.get_extra_info('peername')
        addr = getattr(peer, 'unix_socket', str(peer)) if peer else "unix"
        logger.debug(f"Client connected from {addr}")
        try:
            while True:
                len_bytes = await reader.readexactly(4)
                if not len_bytes:
                    break
                msg_len = int.from_bytes(len_bytes, 'big')
                data = await reader.readexactly(msg_len)
                if not data:
                    break
                try:
                    request = json.loads(data.decode('utf-8'))
                except json.JSONDecodeError as e:
                    logger.warning(f"Invalid JSON from client {addr}: {e}")
                    continue

                response = await self._process_request(request)
                resp_data = json.dumps(response).encode('utf-8')
                writer.write(len(resp_data).to_bytes(4, 'big') + resp_data)
                await writer.drain()
        except asyncio.IncompleteReadError:
            pass
        except Exception as e:
            logger.error(f"Error handling client {addr}: {e}")
        finally:
            writer.close()
            try:
                await writer.wait_closed()
            except Exception:
                pass
            logger.debug(f"Client {addr} disconnected")

    async def _process_request(self, request: Dict[str, Any]) -> Dict[str, Any]:
        msg_id = request.get("msg_id")
        method = request.get("method")
        params = request.get("params", {})

        if not msg_id or not method:
            return {"msg_id": msg_id if msg_id else 0, "type": "error", "error": "Missing msg_id or method"}

        async with self._adapter_lock:
            try:
                if method == "connect":
                    return await self._handle_connect(msg_id, params)
                elif method == "disconnect":
                    return await self._handle_disconnect(msg_id, params)
                elif method == "destroy":
                    return await self._handle_destroy(msg_id, params)
                elif method == "get_status":
                    return await self._handle_get_status(msg_id, params)
                elif method == "get_traffic_stats":
                    return await self._handle_get_traffic_stats(msg_id, params)
                elif method == "list_tunnels":
                    return await self._handle_list_tunnels(msg_id, params)
                elif method == "get_capabilities":
                    return await self._handle_get_capabilities(msg_id, params)
                elif method == "shutdown":
                    return await self._handle_shutdown(msg_id, params)
                else:
                    return {"msg_id": msg_id, "type": "error", "error": f"Unknown method: {method}"}
            except Exception as e:
                logger.exception(f"Error processing {method}")
                return {"msg_id": msg_id, "type": "error", "error": str(e)}

    async def _handle_connect(self, msg_id: int, params: Dict[str, Any]) -> Dict[str, Any]:
        config_dict = params.get("config")
        if not config_dict:
            return {"msg_id": msg_id, "type": "error", "error": "Missing config"}
        config = ConnectionConfig.from_dict(config_dict)
        tunnel_name = config.tunnel_name
        # Get username from session attached to adapter
        username = getattr(getattr(self.adapter, 'session', None), 'username', '')

        # Allocate resources from MTM
        alloc_req = {
            "msg_type": "allocate",
            "tunnel_name": tunnel_name,
            "config": config_dict,
            "username": username
        }
        alloc_resp = await self._call_internal(alloc_req)
        if alloc_resp.get("msg_type") != "allocated":
            err = alloc_resp.get("error", "Resource allocation failed")
            return {"msg_id": msg_id, "type": "error", "error": err}
        namespace = alloc_resp.get("namespace")
        if not namespace:
            return {"msg_id": msg_id, "type": "error", "error": "Allocation missing namespace"}

        try:
            tunnel = await self.adapter.connect(config)
            # Inject namespace
            tunnel.namespace = namespace
            return {"msg_id": msg_id, "type": "result", "result": tunnel.to_dict()}
        except Exception as e:
            # If adapter.connect fails after allocation, we should release the resources to avoid leak
            await self._call_internal({"msg_type": "release", "tunnel_name": tunnel_name})
            return {"msg_id": msg_id, "type": "error", "error": str(e)}

    async def _handle_disconnect(self, msg_id: int, params: Dict[str, Any]) -> Dict[str, Any]:
        tunnel_dict = params.get("tunnel")
        if not tunnel_dict:
            return {"msg_id": msg_id, "type": "error", "error": "Missing tunnel"}
        tunnel = Tunnel.from_dict(tunnel_dict)
        try:
            await self.adapter.disconnect(tunnel)
            return {"msg_id": msg_id, "type": "result", "result": {}}
        except Exception as e:
            return {"msg_id": msg_id, "type": "error", "error": str(e)}

    async def _handle_destroy(self, msg_id: int, params: Dict[str, Any]) -> Dict[str, Any]:
        tunnel_dict = params.get("tunnel")
        if not tunnel_dict:
            return {"msg_id": msg_id, "type": "error", "error": "Missing tunnel"}
        tunnel = Tunnel.from_dict(tunnel_dict)
        tunnel_name = tunnel.name
        # Disconnect if connected
        try:
            if tunnel.device:
                await self.adapter.disconnect(tunnel)
        except Exception as e:
            logger.warning(f"Disconnect during destroy: {e}")

        # Release resources
        release_resp = await self._call_internal({"msg_type": "release", "tunnel_name": tunnel_name})
        if release_resp.get("msg_type") != "released":
            # Log but continue
            logger.warning(f"Release failed: {release_resp.get('error')}")
        return {"msg_id": msg_id, "type": "result", "result": {}}

    async def _handle_get_status(self, msg_id: int, params: Dict[str, Any]) -> Dict[str, Any]:
        tunnel_dict = params.get("tunnel")
        if not tunnel_dict:
            return {"msg_id": msg_id, "type": "error", "error": "Missing tunnel"}
        tunnel = Tunnel.from_dict(tunnel_dict)
        try:
            status = await self.adapter.get_status(tunnel)
            return {"msg_id": msg_id, "type": "result", "result": status.value}
        except Exception as e:
            return {"msg_id": msg_id, "type": "error", "error": str(e)}

    async def _handle_get_traffic_stats(self, msg_id: int, params: Dict[str, Any]) -> Dict[str, Any]:
        tunnel_dict = params.get("tunnel")
        if not tunnel_dict:
            return {"msg_id": msg_id, "type": "error", "error": "Missing tunnel"}
        tunnel = Tunnel.from_dict(tunnel_dict)
        try:
            bytes_in, bytes_out = await self.adapter.get_traffic_stats(tunnel)
            return {"msg_id": msg_id, "type": "result", "result": {"bytes_in": bytes_in, "bytes_out": bytes_out}}
        except Exception as e:
            return {"msg_id": msg_id, "type": "error", "error": str(e)}

    async def _handle_list_tunnels(self, msg_id: int, params: Dict[str, Any]) -> Dict[str, Any]:
        try:
            tunnels = await self.adapter.list_tunnels()
            return {"msg_id": msg_id, "type": "result", "result": [t.to_dict() for t in tunnels]}
        except Exception as e:
            return {"msg_id": msg_id, "type": "error", "error": str(e)}

    async def _handle_get_capabilities(self, msg_id: int, params: Dict[str, Any]) -> Dict[str, Any]:
        try:
            caps = await self.adapter.get_capabilities()
            # Convert to dict
            if hasattr(caps, '__dataclass_fields__'):
                caps_dict = caps.__dict__.copy()
            else:
                caps_dict = caps
            return {"msg_id": msg_id, "type": "result", "result": caps_dict}
        except Exception as e:
            return {"msg_id": msg_id, "type": "error", "error": str(e)}

    async def _handle_shutdown(self, msg_id: int, params: Dict[str, Any]) -> Dict[str, Any]:
        try:
            await self.adapter.cleanup()
            # Stop server after response
            asyncio.create_task(self.stop())
            return {"msg_id": msg_id, "type": "result", "result": {}}
        except Exception as e:
            return {"msg_id": msg_id, "type": "error", "error": str(e)}
