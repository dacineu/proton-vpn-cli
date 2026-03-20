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
import shutil
import signal
import sys
import os
import secrets
from pathlib import Path
from typing import Any, Dict, List, Optional

from libvpnmanager.sessions import SessionManager, Session
from libvpnmanager.sessions.dummy import DummySession
from libvpnmanager.models.config import ConnectionConfig
from libvpnmanager.models.exceptions import (
    TunnelError, TunnelExistsError, TunnelNotFoundError,
    AdapterNotFoundError, AdapterError, AccessDeniedError,
    AuthenticationError, ConfigurationError
)
from libvpnmanager.routing import NetworkNamespaceRouting
from libvpnmanager.ipc import get_server_transport, TransportConfig, list_transports
from .adapter_registry import AdapterRegistry
from .resource_allocator import ResourceAllocator

logger = logging.getLogger(__name__)

# Known adapter types and their static capabilities
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

    def __init__(self, enabled_adapters=None, ipc_transport='unix-socket'):
        self.session_manager = SessionManager()
        self.routing = NetworkNamespaceRouting()
        self.adapter_registry = AdapterRegistry()
        self.resource_allocator = ResourceAllocator(self.routing)
        self.transport = None
        self.running = False
        self._shutdown_event = asyncio.Event()
        self.enabled_adapters = enabled_adapters
        self.ipc_transport = ipc_transport or os.getenv('PROTONVPN_IPC', 'unix-socket')
        self._adapter_dir = Path("/run/mtm/adapters")
        self._internal_socket = "/run/mtm/internal.sock"
        self._pending_sessions: Dict[tuple[str,str], Session] = {}  # cache sessions during login

    def _find_adapter_executable(self, adapter_type: str) -> Optional[str]:
        exe_name = f"mtm-adapter-{adapter_type}"
        # Check MTM_ADAPTER_DIR first
        env_dir = os.getenv('MTM_ADAPTER_DIR')
        if env_dir:
            candidate = Path(env_dir) / exe_name
            if candidate.is_file() and os.access(candidate, os.X_OK):
                return str(candidate)
        return shutil.which(exe_name)

    async def _spawn_adapter(self, adapter_type: str, session_name: str, session: Session, control_socket: str, internal_socket: str) -> asyncio.subprocess.Process:
        """Spawn an adapter subprocess."""
        exe = self._find_adapter_executable(adapter_type)
        if not exe:
            raise AdapterError(f"Adapter executable for '{adapter_type}' not found")

        # Prepare environment
        env = os.environ.copy()
        env.update({
            'MTM_INTERNAL_SOCKET': internal_socket,
            'MTM_CONTROL_SOCKET': control_socket,
            'MTM_ADAPTER_TYPE': adapter_type,
            'MTM_SESSION_NAME': session_name,
            'MTM_SESSION_DATA': json.dumps(session.to_dict()),
        })

        # Start process
        try:
            proc = await asyncio.create_subprocess_exec(
                exe,
                env=env,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
            )
            logger.info(f"Spawned adapter {adapter_type} (session={session_name}) PID={proc.pid}")
            # Register with adapter_registry (PID known)
            self.adapter_registry.register(pid=proc.pid, adapter_type=adapter_type, session_name=session_name,
                                          process=proc, control_socket=control_socket)
            # Note: We do not wait; the adapter will connect to internal socket automatically on startup via a background task in its code? Actually the adapter code needs to initiate that connection. We'll have adapter code do that.
            return proc
        except Exception as e:
            raise AdapterError(f"Failed to start adapter: {e}")

    async def _ensure_adapter(self, adapter_type: str, session_name: str, session: Session) -> str:
        """Ensure an adapter instance is running for the given session; return control socket path."""
        # Check if already running
        endpoint = await self.adapter_registry.get_adapter_endpoint(adapter_type, session_name)
        if endpoint:
            return endpoint
        # Need to spawn
        if not self._adapter_dir.exists():
            self._adapter_dir.mkdir(parents=True, exist_ok=True)
        control_socket = str(self._adapter_dir / f"{adapter_type}-{session_name}.sock")
        # Ensure clean stale socket
        try:
            Path(control_socket).unlink(missing_ok=True)
        except Exception as e:
            logger.warning(f"Could not remove stale socket {control_socket}: {e}")
        try:
            proc = await self._spawn_adapter(adapter_type, session_name, session, control_socket, self._internal_socket)
        except Exception as e:
            logger.error(f"Failed to spawn adapter: {e}")
            raise
        return control_socket

    # Public IPC methods (called by clients)

    async def list_adapters(self) -> List[str]:
        """List available adapter types (those with executables)."""
        if self.enabled_adapters is not None:
            return [a for a in self.enabled_adapters if self._find_adapter_executable(a)]
        # Auto-detect all known types that have executables
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
        """
        Get the control socket path for an adapter instance.
        This will spawn the adapter if not already running.
        """
        # Check if adapter type is available
        if adapter_type not in await self.list_adapters():
            raise AdapterNotFoundError(f"Adapter '{adapter_type}' not available")
        # Validate session exists and belongs to user
        session = await self.session_manager.load_session(adapter_type, session_name, username)
        # Ensure adapter running
        endpoint = await self._ensure_adapter(adapter_type, session_name, session)
        return endpoint

    async def list_sessions(self, username: str, adapter: str = "", all_users: bool = False) -> List[Dict[str, Any]]:
        """List sessions."""
        # Simplified: just delegate to session_manager
        session_infos = await self.session_manager.list_sessions(adapter=adapter if adapter else None, username=username if not all_users else None)
        return [si.to_dict() for si in session_infos]

    async def login(self, adapter: str, session_name: str, username: str, password: str, twofa_code: str = "") -> Dict[str, Any]:
        """Create a new session by logging in."""
        # For now, create a dummy session; actual login would be adapter-specific
        # In a real implementation, we'd call adapter-specific login logic, perhaps via a temporary adapter?
        # Here we simulate success.
        session = DummySession(adapter=adapter, session_name=session_name, username=username, metadata={"password": password})
        await self.session_manager.save_session(session)
        info = SessionInfo(adapter=adapter, session_name=session_name, username=username, status="active")
        return info.to_dict()

    async def logout(self, adapter: str, session_name: str, username: str) -> bool:
        """Logout and remove a session."""
        # Verify ownership? session_manager.logout handles it
        success = await self.session_manager.logout(adapter, session_name, username)
        return success

    async def ping(self) -> bool:
        """Health check."""
        return True

    async def start(self):
        """Start the daemon."""
        logger.info("Starting MTM daemon...")

        # Start internal resource allocator
        await self.resource_allocator.start()
        # Set up the resource allocator to use the adapter_registry for auth
        self.resource_allocator.set_adapter_registry(self.adapter_registry)

        # Start IPC transport(s)
        transports = self.ipc_transport.split(',') if isinstance(self.ipc_transport, str) else self.ipc_transport
        self.transport = []
        for transport_type in transports:
            transport_type = transport_type.strip()
            if not transport_type:
                continue
            try:
                config = TransportConfig(transport_type)
                # Use self as the manager (exposes IPC methods)
                server = get_server_transport(transport_type, self, config)
                await server.start()
                self.transport.append(server)
                logger.info(f"IPC transport '{transport_type}' started")
            except Exception as e:
                logger.error(f"Failed to start IPC transport '{transport_type}': {e}")
                raise

        # Start adapter cleanup background task
        await self.adapter_registry.start_cleanup_task()

        # Handle shutdown signals
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
    asyncio.run(main())
