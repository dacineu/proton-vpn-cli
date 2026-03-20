"""Enhanced Tunnel Manager with multi-user and session support.

This version extends the original TunnelManager to support:
  - Multiple adapters per session (different Proton accounts, Psiphon, WireGuard)
  - Session management through SessionManager
  - User ownership and permissions
  - Listing tunnels across users (for admins)
"""

import asyncio
import logging
from datetime import datetime
from typing import Dict, List, Optional

from .models.tunnel import Tunnel
from .models.config import ConnectionConfig
from .models.status import TunnelStatus
from .models.exceptions import (
    TunnelError,
    TunnelExistsError,
    TunnelNotFoundError,
    AdapterNotFoundError,
    AdapterError,
    AccessDeniedError,
)
from .adapters.base import VPNAdapter, AdapterCapabilities
from .routing.base import RoutingStrategy
from .sessions import SessionManager, Session

logger = logging.getLogger(__name__)


class TunnelManager:
    """
    Orchestrates VPN adapters, sessions, and routing strategies.

    Enhanced for multi-user, multi-backend support.

    Lifecycle:
        1. Create manager with routing_strategy and session_manager
        2. (No manual adapter registration - adapters created on-demand from sessions)
        3. create_tunnel(config, username) - creates tunnel using specified session
        4. connect_tunnel(tunnel_name, username) - connects
        5. list_tunnels(username, all_users) - query
        6. disconnect_tunnel, destroy_tunnel
        7. shutdown()

    Thread-safe: All public methods protected by asyncio.Lock.
    """

    def __init__(
        self,
        routing_strategy: RoutingStrategy,
        session_manager: Optional[SessionManager] = None
    ):
        """
        Initialize tunnel manager.

        Args:
            routing_strategy: RoutingStrategy instance (e.g., NetworkNamespaceRouting)
            session_manager: Optional SessionManager (created if None)
        """
        self.routing = routing_strategy
        self.session_manager = session_manager or SessionManager()
        # (adapter_type, session_name) -> VPNAdapter instance
        self._adapters: Dict[Tuple[str, str], VPNAdapter] = {}
        # adapter_type -> VPNAdapter class
        self._adapter_types: Dict[str, type] = {}
        # tunnel_name -> Tunnel
        self.tunnels: Dict[str, Tunnel] = {}
        self._lock = asyncio.Lock()
        self._running = True

    def _is_admin(self, username: str) -> bool:
        """Check if user is in sudo/wheel group."""
        import grp
        try:
            admin_groups = ["sudo", "wheel", "admin", "adm"]
            user_groups = [g.gr_name for g in grp.getgrall() if username in g.gr_mem]
            return any(g in admin_groups for g in user_groups)
        except Exception:
            return False

    def register_adapter_type(self, adapter_type: str, adapter_class: type) -> None:
        """
        Register an adapter type with the manager.

        Args:
            adapter_type: String identifier (e.g., "proton", "wireguard")
            adapter_class: VPNAdapter subclass
        """
        if not issubclass(adapter_class, VPNAdapter):
            raise ValueError(f"{adapter_class} must be a subclass of VPNAdapter")
        self._adapter_types[adapter_type] = adapter_class

    async def _get_adapter_for_tunnel(
        self,
        adapter_type: str,
        session_name: str,
        username: str
    ) -> VPNAdapter:
        """
        Get or create adapter for given session.

        Args:
            adapter_type: "proton", "psiphon", "wireguard"
            session_name: Session identifier
            username: OS user who owns this session

        Returns:
            VPNAdapter instance (shared among tunnels using same session)
        """
        key = (adapter_type, session_name)
        if key not in self._adapters:
            # Load session to get credentials
            session = await self.session_manager.load_session(
                adapter_type, session_name, username
            )

            # Get adapter class from registry
            if adapter_type not in self._adapter_types:
                raise AdapterNotFoundError(f"Adapter '{adapter_type}' not registered")

            adapter_class = self._adapter_types[adapter_type]
            adapter = adapter_class(session)
            self._adapters[key] = adapter
        return self._adapters[key]

    async def create_tunnel(
        self,
        config: ConnectionConfig,
        username: str
    ) -> Tunnel:
        """
        Create a new tunnel (but don't connect yet).

        Args:
            config: Connection configuration (must include session_name)
            username: OS user creating this tunnel

        Returns:
            Tunnel object in DISCONNECTED state
        """
        async with self._lock:
            if config.tunnel_name in self.tunnels:
                raise TunnelExistsError(f"Tunnel '{config.tunnel_name}' already exists")

            # Ensure session exists (will raise if not)
            # This also validates credentials
            await self.session_manager.load_session(
                config.adapter,
                config.session_name,
                username
            )

            # Create tunnel object
            tunnel = Tunnel(
                name=config.tunnel_name,
                adapter=config.adapter,
                session_name=config.session_name,
                username=username,
                device="",
                namespace=None,
                metadata={"config": config.to_dict()},
            )
            self.tunnels[config.tunnel_name] = tunnel
            return tunnel

    async def connect_tunnel(
        self,
        tunnel_name: str,
        username: str,
        progress_callback=None
    ) -> Tunnel:
        """
        Connect an existing tunnel.

        Args:
            tunnel_name: Name of tunnel to connect
            username: OS user requesting connection
            progress_callback: Optional progress callback

        Returns:
            Updated Tunnel object

        Raises:
            TunnelNotFoundError: If tunnel doesn't exist
            AccessDeniedError: If user doesn't own tunnel and isn't admin
            AdapterError: If connection fails
        """
        async with self._lock:
            tunnel = self.tunnels.get(tunnel_name)
            if not tunnel:
                raise TunnelNotFoundError(f"Tunnel '{tunnel_name}' not found")

            # Permission check: user must own tunnel OR be admin
            if tunnel.username != username and not self._is_admin(username):
                raise AccessDeniedError(
                    f"Tunnel '{tunnel_name}' owned by '{tunnel.username}'. "
                    f"User '{username}' cannot manage it."
                )

            # Get adapter for this tunnel's session
            adapter = await self._get_adapter_for_tunnel(
                tunnel.adapter,
                tunnel.session_name,
                tunnel.username  # Use session owner's username
            )

            # Get config
            config_dict = tunnel.metadata.get("config", {})
            config = ConnectionConfig.from_dict(config_dict)

            try:
                # Connect via adapter
                connected_tunnel = await adapter.connect(config, progress_callback)

                # Update tunnel object
                tunnel.device = connected_tunnel.device
                tunnel.namespace = connected_tunnel.namespace
                tunnel.endpoint = connected_tunnel.endpoint
                tunnel.connected_at = connected_tunnel.connected_at
                tunnel.metadata.update(connected_tunnel.metadata)

                # Create routing context (namespace)
                routing_metadata = await self.routing.create_tunnel_context(tunnel_name)
                if "namespace" in routing_metadata:
                    tunnel.namespace = routing_metadata["namespace"]

                return tunnel

            except Exception as e:
                # Ensure consistent state
                tunnel.device = ""
                tunnel.namespace = None
                raise AdapterError(f"Failed to connect: {e}") from e

    async def disconnect_tunnel(self, tunnel_name: str, username: str) -> None:
        """
        Disconnect a tunnel (keep configuration).

        Args:
            tunnel_name: Tunnel to disconnect
            username: User requesting disconnect

        Raises:
            TunnelNotFoundError: If tunnel doesn't exist
            AccessDeniedError: If user not authorized
        """
        async with self._lock:
            tunnel = self.tunnels.get(tunnel_name)
            if not tunnel:
                raise TunnelNotFoundError(tunnel_name)

            if tunnel.username != username and not self._is_admin(username):
                raise AccessDeniedError(f"Cannot disconnect tunnel owned by {tunnel.username}")

            # Get adapter
            try:
                adapter = self._adapters.get((tunnel.adapter, tunnel.session_name))
                if adapter:
                    await adapter.disconnect(tunnel)
            except Exception as e:
                print(f"Warning: error disconnecting {tunnel_name}: {e}")

            # Clear state
            tunnel.device = ""
            tunnel.namespace = None
            tunnel.connected_at = None
            tunnel.bytes_in = 0
            tunnel.bytes_out = 0

    async def destroy_tunnel(self, tunnel_name: str, username: str) -> None:
        """
        Completely remove a tunnel.

        Steps:
          1. Disconnect if connected
          2. Clean up routing resources
          3. Remove from tunnel registry

        Args:
            tunnel_name: Tunnel to destroy
            username: User requesting destroy

        Raises:
            TunnelNotFoundError: If tunnel doesn't exist
            AccessDeniedError: If user not authorized
        """
        async with self._lock:
            tunnel = self.tunnels.get(tunnel_name)
            if not tunnel:
                raise TunnelNotFoundError(tunnel_name)

            if tunnel.username != username and not self._is_admin(username):
                raise AccessDeniedError(f"Cannot destroy tunnel owned by {tunnel.username}")

            # Disconnect if needed
            if tunnel.device:
                try:
                    adapter = self._adapters.get((tunnel.adapter, tunnel.session_name))
                    if adapter:
                        await adapter.disconnect(tunnel)
                except Exception as e:
                    print(f"Warning: error during disconnect: {e}")

            # Clean up routing
            metadata = {"namespace": tunnel.namespace} if tunnel.namespace else {}
            try:
                await self.routing.destroy_tunnel_context(tunnel_name, metadata)
            except Exception as e:
                print(f"Warning: error destroying routing context: {e}")

            # Remove from registry
            del self.tunnels[tunnel_name]

            # Check if adapter (for this session) is still needed
            adapter_key = (tunnel.adapter, tunnel.session_name)
            if adapter_key in self._adapters:
                remaining = [t for t in self.tunnels.values() if (t.adapter, t.session_name) == adapter_key]
                if not remaining:
                    # No more tunnels using this adapter; clean it up
                    adapter = self._adapters[adapter_key]
                    try:
                        await adapter.cleanup()
                        logger.info(f"Cleaned up idle adapter {adapter_key}")
                    except Exception as e:
                        logger.warning(f"Error cleaning up adapter {adapter_key}: {e}")
                    finally:
                        del self._adapters[adapter_key]

    async def list_tunnels(
        self,
        username: Optional[str] = None,
        all_users: bool = False
    ) -> List[Tunnel]:
        """
        List tunnels.

        Args:
            username: If provided, only tunnels for this user (unless all_users=True)
            all_users: If True, return all tunnels (admin only)

        Returns:
            List of Tunnel objects

        Raises:
            AccessDeniedError: If non-admin tries to list all users
        """
        async with self._lock:
            tunnels = list(self.tunnels.values())

            if all_users:
                if not self._is_admin(username):
                    raise AccessDeniedError("Only admins can list all users' tunnels")
                return tunnels

            if username:
                tunnels = [t for t in tunnels if t.username == username]

            return tunnels

    async def get_tunnel(self, tunnel_name: str, username: Optional[str] = None) -> Optional[Tunnel]:
        """
        Get a specific tunnel by name.

        Args:
            tunnel_name: Tunnel identifier
            username: If provided, verify tunnel belongs to this user (or admin)

        Returns:
            Tunnel or None if not found
        """
        async with self._lock:
            tunnel = self.tunnels.get(tunnel_name)
            if tunnel and username:
                if tunnel.username != username and not self._is_admin(username):
                    raise AccessDeniedError(f"Tunnel belongs to {tunnel.username}")
            return tunnel

    async def get_status(self, tunnel_name: str, username: str) -> TunnelStatus:
        """
        Get connection status for a tunnel.

        Args:
            tunnel_name: Tunnel identifier
            username: Requesting user

        Returns:
            TunnelStatus
        """
        tunnel = await self.get_tunnel(tunnel_name, username)
        if not tunnel or not tunnel.device:
            return TunnelStatus.DISCONNECTED

        adapter = await self._get_adapter_for_tunnel(
            tunnel.adapter,
            tunnel.session_name,
            tunnel.username
        )
        return await adapter.get_status(tunnel)

    async def get_traffic_stats(
        self, tunnel_name: str, username: str
    ) -> Tuple[int, int]:
        """
        Get traffic statistics.

        Args:
            tunnel_name: Tunnel identifier
            username: Requesting user

        Returns:
            (bytes_in, bytes_out)
        """
        tunnel = await self.get_tunnel(tunnel_name, username)
        if not tunnel:
            raise TunnelNotFoundError(tunnel_name)

        adapter = await self._get_adapter_for_tunnel(
            tunnel.adapter,
            tunnel.session_name,
            tunnel.username
        )
        return await adapter.get_traffic_stats(tunnel)

    async def list_adapters(self) -> List[str]:
        """List supported adapter types."""
        return list(self._adapter_types.keys())

    async def get_adapter_capabilities(self, adapter: str) -> AdapterCapabilities:
        """
        Get capabilities for an adapter type.

        Args:
            adapter: Adapter name (e.g., "proton", "psiphon")

        Returns:
            AdapterCapabilities object

        Raises:
            AdapterNotFoundError: If adapter not supported
        """
        # We can define static capabilities per adapter type
        # These should match what the actual adapter reports
        capabilities_map = {
            "dummy": AdapterCapabilities(
                multi_tunnel=True,
                supports_protocols=["dummy"],
                max_tunnels=None,
                supports_per_app_routing=False,
                supports_kill_switch=False,
                supports_dns_isolation=False,
            ),
            "proton": AdapterCapabilities(
                multi_tunnel=True,
                supports_protocols=["wireguard", "openvpn-udp", "openvpn-tcp"],
                max_tunnels=10,  # Proton allows ~10 simultaneous devices
                supports_per_app_routing=False,
                supports_kill_switch=True,
                supports_dns_isolation=True,
            ),
            "psiphon": AdapterCapabilities(
                multi_tunnel=True,
                supports_protocols=["tcp", "udp", "ssh"],
                max_tunnels=None,  # Unlimited?
                supports_per_app_routing=False,
                supports_kill_switch=False,
                supports_dns_isolation=True,
            ),
            "wireguard": AdapterCapabilities(
                multi_tunnel=True,
                supports_protocols=["wireguard"],
                max_tunnels=None,
                supports_per_app_routing=False,
                supports_kill_switch=False,  # Need to implement
                supports_dns_isolation=False,  # WireGuard doesn't manage DNS
            ),
        }

        if adapter not in capabilities_map:
            raise AdapterNotFoundError(f"Adapter '{adapter}' not found")

        return capabilities_map[adapter]

    async def shutdown(self) -> None:
        """
        Graceful shutdown: disconnect all tunnels, cleanup adapters.
        """
        async with self._lock:
            # Disconnect all active tunnels
            for tunnel in list(self.tunnels.values()):
                if tunnel.device:
                    try:
                        adapter = self._adapters.get((tunnel.adapter, tunnel.session_name))
                        if adapter:
                            await adapter.disconnect(tunnel)
                    except Exception as e:
                        print(f"Error disconnecting {tunnel.name}: {e}")

            # Clear tunnels
            self.tunnels.clear()

            # Cleanup adapters
            for adapter in self._adapters.values():
                try:
                    await adapter.cleanup()
                except Exception as e:
                    print(f"Error during adapter cleanup: {e}")
            self._adapters.clear()
