#!/usr/bin/env python3
"""Resource Allocator: internal API for adapters to request OS resources."""

import asyncio
import json
import logging
import os
import struct
import socket as _socket
from typing import Any, Dict, Optional

from libvpnmanager.routing import NetworkNamespaceRouting
from libvpnmanager.models.exceptions import NamespaceError
from .adapter_registry import AdapterRegistry

logger = logging.getLogger(__name__)

# Credentials structure for SO_PEERCRED (pid, uid, gid)
_CRED_STRUCT = '3i'
_CRED_SIZE = struct.calcsize(_CRED_STRUCT)


class ResourceAllocator:
    """Manages allocation and release of network resources (namespaces)."""

    def __init__(self, routing: NetworkNamespaceRouting, socket_path: str = "/run/mtm/internal.sock"):
        self.routing = routing
        self.socket_path = socket_path
        self._server: Optional[asyncio.Server] = None
        self._adapter_registry = None  # type: Optional[AdapterRegistry]
        self._authenticated: set[asyncio.StreamWriter] = set()

    def set_adapter_registry(self, registry):
        """Set the adapter registry for authentication."""
        self._adapter_registry = registry

    async def start(self):
        Path(self.socket_path).parent.mkdir(parents=True, exist_ok=True)
        try:
            os.unlink(self.socket_path)
        except FileNotFoundError:
            pass
        except PermissionError:
            pass

        self._server = await asyncio.start_unix_server(self._handle_client, self.socket_path)
        try:
            os.chmod(self.socket_path, 0o660)
        except Exception as e:
            logger.warning(f"Could not set socket permissions: {e}")
        logger.info(f"Resource allocator listening on {self.socket_path}")

    async def stop(self):
        if self._server:
            self._server.close()
            await self._server.wait_closed()
            self._server = None
        try:
            os.unlink(self.socket_path)
        except FileNotFoundError:
            pass

    async def _handle_client(self, reader: asyncio.StreamReader, writer: asyncio.StreamWriter):
        """Handle a connection from an adapter."""
        sock = writer.get_extra_info('socket')
        if sock is None:
            writer.close()
            return

        # Authenticate using SO_PEERCRED
        try:
            cred = sock.getsockopt(_socket.SOL_SOCKET, _socket.SO_PEERCRED, _CRED_SIZE)
            pid, uid, gid = struct.unpack(_CRED_STRUCT, cred)
        except Exception as e:
            logger.warning(f"Failed to get peer credentials: {e}")
            writer.close()
            return

        if self._adapter_registry is None:
            logger.error("Adapter registry not set on resource allocator")
            writer.close()
            return

        adapter = self._adapter_registry.get_by_pid(pid)
        if adapter is None:
            logger.warning(f"Connection from unknown PID {pid}, rejecting")
            writer.close()
            return

        logger.debug(f"Authenticated adapter {adapter.adapter_type} (session={adapter.session_name}, pid={pid})")
        self._authenticated.add(writer)

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
                    logger.warning(f"Invalid JSON from adapter {pid}: {e}")
                    continue

                response = await self._dispatch(request, adapter)
                resp_data = json.dumps(response).encode('utf-8')
                writer.write(len(resp_data).to_bytes(4, 'big') + resp_data)
                await writer.drain()
        except asyncio.IncompleteReadError:
            pass
        except Exception as e:
            logger.error(f"Error in resource allocator client handler (pid={pid}): {e}")
        finally:
            self._authenticated.discard(writer)
            writer.close()
            try:
                await writer.wait_closed()
            except Exception:
                pass

    async def _dispatch(self, request: Dict[str, Any], adapter) -> Dict[str, Any]:
        msg_type = request.get("msg_type")

        # Token validation if expected_session_token is set
        if adapter.expected_session_token is not None:
            client_token = request.get('session_token')
            if client_token != adapter.expected_session_token:
                logger.warning(f"Invalid session token from adapter {adapter.adapter_type}")
                return {"msg_type": "error", "error": "INVALID_SESSION", "code": "INVALID_SESSION"}

        if msg_type == "allocate":
            return await self._handle_allocate(request, adapter)
        elif msg_type == "register":
            return await self._handle_register(request, adapter)
        elif msg_type == "release":
            return await self._handle_release(request, adapter)
        else:
            return {"msg_type": "error", "error": f"Unknown msg_type: {msg_type}"}

    async def _handle_register(self, request: Dict[str, Any], adapter) -> Dict[str, Any]:
        """Handle adapter registration."""
        session_id = request.get('session_id')
        adapter_type = request.get('adapter_type')
        username = request.get('username')
        if not all([session_id, adapter_type, username]):
            return {'msg_type': 'error', 'error': 'Missing register fields'}
        # Store registration info in adapter instance
        adapter.session_id = session_id
        adapter.username = username
        adapter.tunnels = set()
        # Store expected session token if provided (Phase 1: may be None initially)
        adapter.expected_session_token = request.get('session_token')
        logger.info(f'Adapter registered: {adapter_type} user={username} session={session_id}')
        return {'msg_type': 'registered', 'control_socket': self.socket_path}

    async def _handle_allocate(self, request: Dict[str, Any], adapter) -> Dict[str, Any]:
        tunnel_name = request.get("tunnel_name")
        config = request.get("config", {})
        username = request.get("username", "")
        if not tunnel_name:
            return {"msg_type": "error", "error": "Missing tunnel_name"}
        try:
            metadata = await self.routing.create_tunnel_context(tunnel_name)
            namespace = metadata.get("namespace")
            if not namespace:
                raise NamespaceError("No namespace returned")
            logger.info(f"Allocated namespace {namespace} for tunnel {tunnel_name} (adapter={adapter.adapter_type}, user={username})")
            return {
                "msg_type": "allocated",
                "tunnel_name": tunnel_name,
                "namespace": namespace,
            }
        except Exception as e:
            logger.error(f"Allocation failed for tunnel {tunnel_name}: {e}")
            return {"msg_type": "error", "error": str(e)}

    async def _handle_release(self, request: Dict[str, Any], adapter) -> Dict[str, Any]:
        tunnel_name = request.get("tunnel_name")
        if not tunnel_name:
            return {"msg_type": "error", "error": "Missing tunnel_name"}
        try:
            await self.routing.destroy_tunnel_context(tunnel_name, {})
            logger.info(f"Released resources for tunnel {tunnel_name} (adapter={adapter.adapter_type})")
            return {"msg_type": "released", "tunnel_name": tunnel_name}
        except Exception as e:
            logger.error(f"Release failed for tunnel {tunnel_name}: {e}")
            return {"msg_type": "error", "error": str(e)}
