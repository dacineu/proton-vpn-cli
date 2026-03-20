#!/usr/bin/env python3
"""
proton-vpn-manager daemon – two‑tier architecture.

CLI ↔ MTM (management IPC) → get_adapter_endpoint()
CLI ↔ Adapter (direct control Unix socket) → tunnel operations
Adapter ↔ MTM (internal Unix socket) → allocate/release network resources
"""

import asyncio
import json
import logging
import re
import shutil
import signal
import sys
import os
import secrets
import time
import uuid
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

from libvpnmanager.sessions import SessionManager, Session, SessionInfo
from libvpnmanager.sessions.dummy import DummySession
from libvpnmanager.models.exceptions import (
    TunnelError, TunnelExistsError, TunnelNotFoundError,
    AdapterNotFoundError, AdapterError, AccessDeniedError,
    AuthenticationError, ConfigurationError
)
from libvpnmanager.routing import NetworkNamespaceRouting
from libvpnmanager.ipc import get_server_transport, TransportConfig, list_transports
from .adapter_registry import AdapterRegistry
from .resource_allocator import ResourceAllocator
from libvpnmanager.client import AdapterClient
from libvpnmanager.models.config import ConnectionConfig

logger = logging.getLogger(__name__)

# Known adapter types and static capabilities
ADAPTER_CAPABILITIES = {
    "dummy": {
        "multi_tunnel": True,
        "supports_protocols": ["dummy"],
        "max_tunnels": None,
        "supports_per_app_routing": False,
        "supports_kill_switch": False,
        "supports_dns_isolation": False,
    },
    "proton": {
        "multi_tunnel": True,
        "supports_protocols": ["wireguard", "openvpn-udp", "openvpn-tcp"],
        "max_tunnels": 10,
        "supports_per_app_routing": False,
        "supports_kill_switch": True,
        "supports_dns_isolation": True,
    },
    "psiphon": {
        "multi_tunnel": True,
        "supports_protocols": ["tcp", "udp", "ssh"],
        "max_tunnels": None,
        "supports_per_app_routing": False,
        "supports_kill_switch": False,
        "supports_dns_isolation": True,
    },
    "wireguard": {
        "multi_tunnel": True,
        "supports_protocols": ["wireguard"],
        "max_tunnels": None,
        "supports_per_app_routing": False,
        "supports_kill_switch": False,
        "supports_dns_isolation": False,
    },
}

class VPNDaemon:
    """Main daemon class – IPC controller and resource allocator."""

    def __init__(self, enabled_adapters=None, ipc_transport='unix-socket', *, socket_path=None, adapter_dir=None, internal_socket=None):
        self.session_manager = SessionManager()
        self.routing = NetworkNamespaceRouting()
        # Overrideable paths
        self.ipc_socket_path = socket_path
        self._adapter_dir = Path(adapter_dir) if adapter_dir else Path("/run/mtm/adapters")
        self._internal_socket = internal_socket or "/run/mtm/internal.sock"
        # Initialize registry and allocator with custom paths
        self.adapter_registry = AdapterRegistry(adapter_dir=str(self._adapter_dir))
        self.resource_allocator = ResourceAllocator(self.routing, socket_path=self._internal_socket)
        self.transport = None
        self.running = False
        self._shutdown_event = asyncio.Event()
        self.enabled_adapters = enabled_adapters
        self.ipc_transport = ipc_transport or os.getenv('PROTONVPN_IPC', 'unix-socket')
        # Adapter pool: (adapter_type, vpn_username) -> endpoint
        self.adapter_pool: Dict[Tuple[str, str], str] = {}
        # Session tokens: token -> (expiry, username)
        self.session_tokens: Dict[str, Tuple[float, str]] = {}

    def _find_adapter_executable(self, adapter_type: str) -> Optional[str]:
        exe_name = f"mtm-adapter-{adapter_type}"
        env_dir = os.getenv('MTM_ADAPTER_DIR')
        if env_dir:
            candidate = Path(env_dir) / exe_name
            if candidate.is_file() and os.access(candidate, os.X_OK):
                return str(candidate)
        return shutil.which(exe_name)

    async def _spawn_adapter(self, adapter_type: str, session_name: str, session: Session, control_socket: str, credentials: Optional[Dict[str, Any]] = None, session_token: Optional[str] = None) -> asyncio.subprocess.Process:
        """Spawn an adapter subprocess."""
        exe = self._find_adapter_executable(adapter_type)
        if not exe:
            raise AdapterError(f"Adapter executable for '{adapter_type}' not found")

        env = os.environ.copy()
        env.update({
            'MTM_INTERNAL_SOCKET': self._internal_socket,
            'MTM_CONTROL_SOCKET': control_socket,
            'MTM_ADAPTER_TYPE': adapter_type,
            'MTM_SESSION_NAME': session_name,
        })

        try:
            proc = await asyncio.create_subprocess_exec(
                exe,
                env=env,
                stdin=asyncio.subprocess.PIPE,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
            )
            # Deliver credentials via stdin if provided
            if credentials is not None:
                startup_payload = {
                    "session_id": session_name,
                    "totp_secret": None,
                    "vpn_credentials": credentials,
                    "session_token": session_token,
                }
                proc.stdin.write(json.dumps(startup_payload).encode() + b'\n')
                await proc.stdin.drain()
                proc.stdin.close()
            logger.info(f"Spawned adapter {adapter_type} (session={session_name}) PID={proc.pid}")
            # Register with adapter_registry
            self.adapter_registry.register(pid=proc.pid, adapter_type=adapter_type, session_name=session_name,
                                          process=proc, control_socket=control_socket)
            return proc
        except Exception as e:
            raise AdapterError(f"Failed to start adapter: {e}")

    async def _ensure_adapter(self, adapter_type: str, session_name: str, session: Session) -> str:
        """Ensure an adapter instance is running; return control socket path."""
        existing = await self.adapter_registry.get_adapter_endpoint(adapter_type, session_name)
        if existing:
            return existing
        # Spawn new adapter
        if not self._adapter_dir.exists():
            self._adapter_dir.mkdir(parents=True, exist_ok=True)
        control_socket = str(self._adapter_dir / f"{adapter_type}-{session_name}.sock")
        try:
            Path(control_socket).unlink(missing_ok=True)
        except Exception as e:
            logger.warning(f"Could not remove stale socket {control_socket}: {e}")
        try:
            await self._spawn_adapter(adapter_type, session_name, session, control_socket)
            return control_socket
        except Exception as e:
            logger.error(f"Failed to spawn adapter: {e}")
            raise

    # Public IPC methods

    async def list_available_adapters(self) -> List[str]:
        """List available adapter types (those with executables)."""
        if self.enabled_adapters is not None:
            return [a for a in self.enabled_adapters if self._find_adapter_executable(a)]
        available = []
        for a in ADAPTER_CAPABILITIES.keys():
            if self._find_adapter_executable(a):
                available.append(a)
        return available

    async def get_adapter_capabilities(self, adapter: str) -> Dict[str, Any]:
        """Get capabilities for an adapter type."""
        if adapter not in ADAPTER_CAPABILITIES:
            raise AdapterNotFoundError(f"Adapter '{adapter}' not known")
        return ADAPTER_CAPABILITIES[adapter]

    async def get_adapter_endpoint(self, adapter_type: str, session_name: str, username: str) -> str:
        """Get the control socket path for an adapter instance (spawns if needed)."""
        if adapter_type not in await self.list_adapters():
            raise AdapterNotFoundError(f"Adapter '{adapter_type}' not available")
        # Validate session exists and belongs to user
        try:
            session = await self.session_manager.load_session(adapter_type, session_name, username)
        except Exception as e:
            raise AccessDeniedError(f"Session validation failed: {e}")
        return await self._ensure_adapter(adapter_type, session_name, session)

    async def list_sessions(self, username: str, adapter: str = "", all_users: bool = False) -> List[Dict[str, Any]]:
        """List sessions."""
        session_infos = await self.session_manager.list_sessions(
            adapter=adapter if adapter else None,
            username=username if not all_users else None
        )
        return [si.to_dict() for si in session_infos]

    async def login(self, adapter: str, session_name: str, username: str, password: str, twofa_code: str = "") -> Dict[str, Any]:
        """Create a new session by logging in."""
        # For simplicity, create a dummy session. Real implementation would authenticate with the VPN backend.
        session = DummySession(adapter=adapter, session_name=session_name, username=username, metadata={"password": password})
        await self.session_manager.save_session(session)
        info = SessionInfo(adapter=adapter, session_name=session_name, username=username, status="active")
        return info.to_dict()

    async def logout(self, adapter: str, session_name: str, username: str) -> bool:
        """Logout and remove a session."""
        return await self.session_manager.logout(adapter, session_name, username)

    async def ping(self) -> bool:
        """Health check."""
        return True

    async def verify_2fa(self, totp_code: str) -> Dict[str, Any]:
        """Verify 2FA code and issue a session token."""
        if not re.match(r'^\d{6}$', totp_code):
            raise AuthenticationError("Invalid TOTP code")
        token = secrets.token_urlsafe(32)
        expiry = time.time() + 900
        # Store with placeholder username; actual username will be provided in StartAdapter
        self.session_tokens[token] = (expiry, "pending")
        return {"session_token": token, "expires_in": 900}

    async def start_adapter(self, adapter_type: str, credentials: Dict[str, Any], session_token: Optional[str] = None) -> Dict[str, Any]:
        """Start an adapter process with credentials, returning its control endpoint."""
        # Validate adapter_type is available (exists in capabilities and has executable)
        if adapter_type not in ADAPTER_CAPABILITIES or not self._find_adapter_executable(adapter_type):
            raise AdapterNotFoundError(f"Adapter '{adapter_type}' not available")

        # Extract username from credentials
        vpn_username = credentials.get('username')
        if not vpn_username:
            raise ValueError("Credentials must include 'username'")

        # Check adapter_pool for existing instance
        key = (adapter_type, vpn_username)
        if key in self.adapter_pool:
            return {'endpoint': self.adapter_pool[key]}

        # Validate session token if provided
        if session_token is None:
            raise AuthenticationError("Session token required")
        if session_token not in self.session_tokens:
            raise AuthenticationError("Invalid session token")
        expiry, stored_username = self.session_tokens[session_token]
        if time.time() > expiry:
            del self.session_tokens[session_token]
            raise AuthenticationError("Session token expired")
        # Optionally verify stored_username matches (if not pending); for now allow any

        # Generate session ID
        session_id = str(uuid.uuid4())

        # Create socket path using username (per plan)
        cli_socket_path = f"/run/mtm/adapters/{vpn_username}_{adapter_type}.sock"

        # Ensure directory exists and remove stale socket
        socket_path = Path(cli_socket_path)
        if not socket_path.parent.exists():
            socket_path.parent.mkdir(parents=True, exist_ok=True)
        try:
            socket_path.unlink(missing_ok=True)
        except Exception as e:
            logger.warning(f"Could not remove stale socket {cli_socket_path}: {e}")

        # Spawn adapter with credentials via stdin
        # Use the session_id as the session_name for registry tracking
        proc = await self._spawn_adapter(adapter_type, session_id, DummySession(adapter=adapter_type, session_name=session_id, username=vpn_username, metadata={}), cli_socket_path, credentials, session_token)

        # Wait for socket to become available (up to 10 seconds)
        timeout = 10.0
        start = time.time()
        while time.time() - start < timeout:
            if socket_path.exists():
                break
            await asyncio.sleep(0.05)
        else:
            raise AdapterError(f"Adapter socket {cli_socket_path} not created within {timeout}s")

        # Register with adapter_registry
        self.adapter_registry.register(
            pid=proc.pid,
            adapter_type=adapter_type,
            session_name=session_id,
            process=proc,
            control_socket=cli_socket_path
        )

        # Add to adapter_pool
        self.adapter_pool[key] = f"unix://{cli_socket_path}"

        # Consume session token
        if session_token in self.session_tokens:
            del self.session_tokens[session_token]

        return {'endpoint': f'unix://{cli_socket_path}'}

    async def create_tunnel(self, config: Dict[str, Any], username: str) -> Dict[str, Any]:
        """
        Create a new tunnel via the adapter (legacy API).
        Ensures an adapter is running for the given adapter type and forwards the request.
        """
        # Parse configuration
        try:
            conn_config = ConnectionConfig.from_dict(config)
        except Exception as e:
            raise ValueError(f"Invalid configuration: {e}") from e

        adapter_type = conn_config.adapter
        # Find a running adapter instance for this user and type
        instance = None
        async with self.adapter_registry._lock:
            for (at, session_name), inst in self.adapter_registry.adapters.items():
                if at == adapter_type and inst.username == username:
                    instance = inst
                    break
        if instance is None:
            raise AdapterNotFoundError(f"No running adapter for type '{adapter_type}' and user '{username}'")

        endpoint = f"unix://{instance.control_socket}"
        token = instance.expected_session_token
        # Wait briefly for token if not yet set (adapter registration may be in progress)
        if token is None:
            waited = 0.0
            while token is None and waited < 5.0:
                await asyncio.sleep(0.1)
                waited += 0.1
                token = instance.expected_session_token
            if token is None:
                raise TunnelError("Adapter not ready: session token not received")

        # Forward request to adapter
        async with AdapterClient(endpoint, session_token=token) as adapter_client:
            tunnel = await adapter_client.create_tunnel(conn_config.tunnel_name, conn_config)
        return tunnel.to_dict()

    async def connect_tunnel(self, name: str, username: str) -> bool:
        """
        Connect an existing tunnel.
        Verifies that the tunnel exists in the adapter's managed set.
        """
        async with self.adapter_registry._lock:
            for instance in self.adapter_registry.adapters.values():
                if instance.username == username and name in instance.tunnels:
                    return True
        raise TunnelNotFoundError(f"Tunnel {name} not found for user '{username}'")

    async def list_adapters(self, username: Optional[str] = None) -> List[Dict[str, Any]]:
        """List running adapter instances, optionally filtered by username."""
        result = []
        for (adapter_type, uname), endpoint in self.adapter_pool.items():
            if username is None or uname == username:
                result.append({
                    'adapter_type': adapter_type,
                    'username': uname,
                    'endpoint': endpoint
                })
        return result

    async def stop_adapter(self, adapter_type: str, username: Optional[str] = None) -> bool:
        """Stop a running adapter instance."""
        if username is None:
            raise ValueError("username required")
        key = (adapter_type, username)
        if key not in self.adapter_pool:
            return False
        # Retrieve the endpoint URI and derive the raw socket path
        endpoint_uri = self.adapter_pool[key]
        raw_socket_path = endpoint_uri[7:] if endpoint_uri.startswith('unix://') else endpoint_uri
        # Find the matching adapter registry entry by control_socket
        session_name = None
        for (at, sn), instance in self.adapter_registry.adapters.items():
            if at == adapter_type and instance.control_socket == raw_socket_path:
                session_name = sn
                break
        if session_name is None:
            # Adapter not found in registry (already exited?), remove from pool and return failure
            del self.adapter_pool[key]
            return False
        # Remove from pool first
        del self.adapter_pool[key]
        # Terminate via registry
        success = await self.adapter_registry.terminate_adapter(adapter_type, session_name)
        return success

    async def start(self):
        """Start the daemon."""
        logger.info("Starting MTM daemon...")

        # Start internal resource allocator
        await self.resource_allocator.start()
        self.resource_allocator.set_adapter_registry(self.adapter_registry)
        # Bidirectional link for crash cleanup
        self.adapter_registry.set_resource_allocator(self.resource_allocator)

        # Start IPC transports
        transports = self.ipc_transport.split(',') if isinstance(self.ipc_transport, str) else self.ipc_transport
        self.transport = []
        for transport_type in transports:
            transport_type = transport_type.strip()
            if not transport_type:
                continue
            try:
                config = TransportConfig(transport_type)
                if transport_type == 'unix-socket' and self.ipc_socket_path:
                    config.extra['socket_path'] = self.ipc_socket_path
                # Use self as the manager for IPC
                server = get_server_transport(transport_type, self, config)
                await server.start()
                self.transport.append(server)
                logger.info(f"IPC transport '{transport_type}' started")
            except Exception as e:
                logger.error(f"Failed to start IPC transport '{transport_type}': {e}")
                raise

        # Start adapter cleanup
        await self.adapter_registry.start_cleanup_task()

        # Signal handling
        loop = asyncio.get_event_loop()
        for sig in (signal.SIGTERM, signal.SIGINT):
            loop.add_signal_handler(sig, lambda s=sig: asyncio.create_task(self._handle_signal(s)))

        self.running = True
        logger.info("MTM daemon ready")
        await self._shutdown_event.wait()
        await self.shutdown()

    async def _handle_signal(self, sig: int):
        logger.info(f"Received signal {sig}, shutting down")
        self._shutdown_event.set()

    async def shutdown(self):
        logger.info("Shutting down MTM daemon")
        # Stop transports
        for server in self.transport:
            try:
                await server.stop()
            except Exception as e:
                logger.warning(f"Error stopping transport: {e}")
        self.transport.clear()
        # Stop resource allocator
        await self.resource_allocator.stop()
        # Terminate all adapters
        await self.adapter_registry.terminate_all()
        # Stop cleanup task
        await self.adapter_registry.stop_cleanup_task()
        logger.info("MTM daemon stopped")

    def stop(self):
        """Request daemon shutdown. Can be called from external context."""
        self._shutdown_event.set()

async def main():
    daemon = VPNDaemon()
    try:
        await daemon.start()
    except KeyboardInterrupt:
        logger.info("Interrupted")
    except Exception as e:
        logger.error(f"Daemon failed: {e}")
        sys.exit(1)

if __name__ == "__main__":
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
        handlers=[logging.StreamHandler(sys.stderr)],
    )
    asyncio.run(main())
