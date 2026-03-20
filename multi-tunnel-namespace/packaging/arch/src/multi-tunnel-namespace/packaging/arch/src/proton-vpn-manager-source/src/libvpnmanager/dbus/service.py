"""D-Bus service for TunnelManager.

This module implements the D-Bus interface that the daemon exports,
allowing CLI and GUI clients to control VPN tunnels.
"""

import asyncio
from datetime import datetime
from typing import Dict, Any, List, Optional

from dbus_next.aio import MessageBus
from dbus_next.service import ServiceInterface, method, signal, dbus_property
from dbus_next import Variant

from ..models.tunnel import Tunnel
from ..models.status import TunnelStatus
from ..models.config import ConnectionConfig
from ..manager import TunnelManager
from ..adapters.base import AdapterCapabilities


def _to_variant(value):
    """Convert a Python value to a dbus_next.Variant with appropriate signature."""
    if value is None:
        return Variant('s', '')
    if isinstance(value, dict):
        # Convert dict to a{sv} where each value is a Variant
        inner = {k: _to_variant(v) for k, v in value.items()}
        return Variant('a{sv}', inner)
    if isinstance(value, str):
        sig = 's'
    elif isinstance(value, bool):
        sig = 'b'
    elif isinstance(value, int):
        sig = 'x'  # int64
    elif isinstance(value, float):
        sig = 'd'
    elif isinstance(value, bytes):
        sig = 'ay'
    elif isinstance(value, datetime):
        # datetime should be converted to ISO string
        sig = 's'
        value = value.isoformat()
    else:
        raise TypeError(f"Unsupported type for Variant: {type(value)}")
    return Variant(sig, value)


class ManagerService(ServiceInterface):
    """
    D-Bus service: org.protonvpn.Manager

    Exposes tunnel management methods over D-Bus.
    """

    def __init__(self, manager: TunnelManager):
        """
        Initialize service.

        Args:
            manager: TunnelManager instance
        """
        super().__init__("org.protonvpn.Manager")
        self.manager = manager
        # For test compatibility, expose interface name
        self._interface_name = "org.protonvpn.Manager"

    # D-Bus methods

    @method()
    async def CreateTunnel(
        self,
        config_dict: "a{sv}",
        username: "s"
    ) -> "a{sv}":
        """
        Create and optionally connect a tunnel.

        Args:
            config_dict: Dictionary of configuration options (as D-Bus variants)
            username: OS username of user creating this tunnel

        Returns:
            Tunnel info dictionary

        Raises:
            TunnelExistsError: If tunnel name already exists
            AdapterNotFoundError: If adapter not found
            ConfigurationError: If config invalid
            PermissionError: If user cannot create tunnel with specified session
        """
        # Convert D-Bus variants to Python types
        config = {k: v.value for k, v in config_dict.items()}

        # Ensure adapter, tunnel_name, and session_name are present
        if "adapter" not in config or "tunnel_name" not in config:
            raise ValueError("adapter, tunnel_name, and session_name are required")

        # Create config object
        connection_config = ConnectionConfig.from_dict(config)

        # Create tunnel (with explicit username for ownership)
        tunnel = await self.manager.create_tunnel(connection_config, username)
        await self.manager.connect_tunnel(tunnel.name, username)

        # Return tunnel info, converting values to Variants
        result = tunnel.to_dict()
        return {k: _to_variant(v) for k, v in result.items()}

    @method()
    async def DestroyTunnel(self, name: "s", username: "s") -> "b":
        """
        Completely remove a tunnel.

        Args:
            name: Tunnel name
            username: User requesting destruction

        Returns:
            True if successful

        Raises:
            TunnelNotFoundError: If tunnel doesn't exist
            PermissionError: If user is not authorized
        """
        await self.manager.destroy_tunnel(name, username)
        self.TunnelStateChanged(name, "destroyed")
        return True

    @method()
    async def ConnectTunnel(self, name: "s", username: "s") -> "b":
        """
        Connect an existing tunnel.

        Args:
            name: Tunnel name
            username: User requesting connection

        Returns:
            True if successful

        Raises:
            TunnelNotFoundError: If tunnel doesn't exist
            PermissionError: If user not authorized
        """
        await self.manager.connect_tunnel(name, username)
        self.TunnelStateChanged(name, "connected")
        return True

    @method()
    async def DisconnectTunnel(self, name: "s", username: "s") -> "b":
        """
        Disconnect a tunnel (keep configuration).

        Args:
            name: Tunnel name
            username: User requesting disconnect

        Returns:
            True if successful

        Raises:
            TunnelNotFoundError: If tunnel doesn't exist
            PermissionError: If user not authorized
        """
        await self.manager.disconnect_tunnel(name, username)
        self.TunnelStateChanged(name, "disconnected")
        return True

    @method()
    async def ListTunnels(
        self,
        username: "s",
        all_users: "b" = False
    ) -> "aa{sv}":
        """
        List tunnels.

        Args:
            username: Requesting user (for permission check)
            all_users: If True, list all tunnels (admin only)

        Returns:
            List of tunnel dictionaries

        Raises:
            PermissionError: If non-admin tries to list all users
        """
        tunnels = await self.manager.list_tunnels(username, all_users)
        result = []
        for tunnel in tunnels:
            d = tunnel.to_dict()
            result.append({k: _to_variant(v) for k, v in d.items()})
        return result

    @method()
    async def GetTunnelStatus(
        self,
        name: "s",
        username: "s"
    ) -> "a{sv}":
        """
        Get detailed status for a tunnel.

        Args:
            name: Tunnel name
            username: Requesting user

        Returns:
            Dictionary with status and optional error message

        Raises:
            TunnelNotFoundError: If tunnel doesn't exist
            PermissionError: If user not authorized
        """
        tunnel = await self.manager.get_tunnel(name, username)
        if not tunnel:
            raise ValueError(f"Tunnel {name} not found")

        status = await self.manager.get_status(name, username)

        result = {
            "name": Variant("s", tunnel.name),
            "status": Variant("s", status.value),
            "adapter": Variant("s", tunnel.adapter),
            "device": Variant("s", tunnel.device),
            "namespace": Variant("s", tunnel.namespace or ""),
            "endpoint": Variant("s", tunnel.endpoint or ""),
            "session_name": Variant("s", tunnel.session_name),
            "owner": Variant("s", tunnel.username),
        }

        if tunnel.connected_at:
            result["connected_at"] = Variant("s", tunnel.connected_at.isoformat())

        return result

    @method()
    async def GetTrafficStats(self, name: "s", username: "s") -> "(tt)":
        """
        Get traffic statistics for a tunnel.

        Args:
            name: Tunnel name
            username: Requesting user

        Returns:
            (bytes_in, bytes_out) tuple

        Raises:
            TunnelNotFoundError: If tunnel doesn't exist
            PermissionError: If user not authorized
        """
        return await self.manager.get_traffic_stats(name, username)

    @method()
    async def ListAdapters(self) -> "as":
        """
        List registered adapter names.

        Returns:
            List of adapter type names
        """
        return await self.manager.list_adapters()

    @method()
    async def GetAdapterCapabilities(self, adapter: "s") -> "a{sv}":
        """
        Get capabilities for an adapter.

        Args:
            adapter: Adapter name

        Returns:
            Dictionary of capabilities
        """
        caps = await self.manager.get_adapter_capabilities(adapter)
        return {
            "multi_tunnel": Variant("b", caps.multi_tunnel),
            "supports_protocols": Variant("as", caps.supports_protocols),
            "max_tunnels": Variant("i", caps.max_tunnels or -1),
            "supports_per_app_routing": Variant("b", caps.supports_per_app_routing),
            "supports_kill_switch": Variant("b", caps.supports_kill_switch),
            "supports_dns_isolation": Variant("b", caps.supports_dns_isolation),
        }

    @method()
    async def Ping(self) -> "b":
        """
        Simple health check.

        Returns:
            True if daemon is alive
        """
        return True

    @method()
    async def ListSessions(
        self,
        username: "s",
        adapter: "s" = "",
        all_users: "b" = False
    ) -> "aa{sv}":
        """
        List available VPN sessions.

        Args:
            username: Requesting user
            adapter: Filter by adapter type (empty = all)
            all_users: If True, list all users' sessions (admin only)

        Returns:
            List of session info dictionaries

        Raises:
            PermissionError: If non-admin tries to list all users
        """
        from ..sessions import SessionInfo

        session_infos = await self.manager.session_manager.list_sessions(
            adapter=adapter if adapter else None,
            username=username if not all_users else None
        )

        result = []
        for info in session_infos:
            d = info.to_dict()
            result.append({k: _to_variant(v) for k, v in d.items()})
        return result

    @method()
    async def Login(
        self,
        adapter: "s",
        session_name: "s",
        username: "s",
        password: "s",
        twofa_code: "s" = ""
    ) -> "a{sv}":
        """
        Create a new session by logging in.

        Args:
            adapter: Adapter type ("proton", "psiphon", etc.)
            session_name: Desired session identifier
            username: VPN account username (email for Proton)
            password: Account password
            twofa_code: Optional 2FA code

        Returns:
            Session info dictionary

        Raises:
            AuthenticationError: If login fails
            ConfigurationError: If adapter doesn't support login
        """
        from ..sessions import Session

        session = await self.manager.session_manager.load_session(
            adapter=adapter,
            session_name=session_name,
            username=username,
            password=password,
            twofa_code=twofa_code if twofa_code else None
        )

        # Save session persistently
        await self.manager.session_manager._save_to_storage(session)

        info = session.to_session_info()
        d = info.to_dict()
        return {k: _to_variant(v) for k, v in d.items()}

    @method()
    async def Logout(
        self,
        adapter: "s",
        session_name: "s",
        username: "s"
    ) -> "b":
        """
        Logout and remove a session.

        Args:
            adapter: Adapter type
            session_name: Session to remove
            username: User requesting logout

        Returns:
            True if successful

        Raises:
            SessionNotFoundError: If session doesn't exist
        """
        success = await self.manager.session_manager.logout(
            adapter=adapter,
            session_name=session_name,
            username=username
        )
        return success

    # D-Bus signals

    @signal()
    def TunnelStateChanged(self, name: "s", state: "s"):
        """
        Emitted when a tunnel's state changes.

        Args:
            name: Tunnel name
            state: New state ("connected", "disconnected", "error", etc.)
        """
        pass

    @signal()
    def TunnelCreated(self, name: "s"):
        """Emitted when a new tunnel is created."""
        pass

    @signal()
    def TunnelDestroyed(self, name: "s"):
        """Emitted when a tunnel is destroyed."""
        pass

    @signal()
    def AdapterRegistered(self, adapter_type: "s", version: "s"):
        """Emitted when a new adapter is registered."""
        pass


async def start_service(manager: TunnelManager, bus: Optional[MessageBus] = None):
    """
    Start the D-Bus service.

    Args:
        manager: TunnelManager instance (already configured with adapters)
        bus: Optional MessageBus instance (for testing)
    """
    if bus is None:
        bus = await MessageBus().connect()

    service = ManagerService(manager)

    # Export interface on the manager object path
    bus.export("/org/protonvpn/Manager", service)

    # Request well-known name
    await bus.request_name("org.protonvpn.Manager")

    print("D-Bus service started: org.protonvpn.Manager on /org/protonvpn/Manager")

    return bus, service
