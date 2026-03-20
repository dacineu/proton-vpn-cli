"""D-Bus client for CLI tools.

Provides a convenient wrapper around the org.protonvpn.Manager D-Bus interface.
"""

from typing import Dict, Any, List, Optional, Tuple
from datetime import datetime

from dbus_next.aio import MessageBus
from dbus_next import Variant
from dbus_next.errors import DBusError as DNextBusError

from ..models.tunnel import Tunnel
from ..models.status import TunnelStatus
from ..models.config import ConnectionConfig
from ..models.exceptions import TunnelError, DBusError
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
        # bytes to bytearray
        value = list(value)
    elif isinstance(value, datetime):
        sig = 's'
        value = value.isoformat()
    else:
        raise TypeError(f"Unsupported type for D-Bus variant: {type(value)}")
    return Variant(sig, value)


class VPNManagerClient:
    """
    Async D-Bus client for the proton-vpn-manager daemon.

    Usage:
        client = VPNManagerClient()
        await client.connect()
        tunnels = await client.list_tunnels()
    """

    def __init__(self, bus: Optional[MessageBus] = None):
        """
        Initialize client.

        Args:
            bus: Optional MessageBus instance (for testing)
        """
        self.bus = bus
        self.proxy = None
        self.connected = False

    async def connect(self):
        """Connect to the D-Bus daemon."""
        if self.bus is None:
            self.bus = await MessageBus().connect()

        # Get proxy object
        proxy = await self.bus.introspect("org.protonvpn.Manager", "/org/protonvpn/Manager")
        self.proxy = self.bus.get_proxy_object(
            "org.protonvpn.Manager", "/org/protonvpn/Manager", proxy
        )
        self.connected = True

    async def disconnect(self):
        """Disconnect from D-Bus."""
        self.proxy = None
        self.connected = False

    # Tunnel management methods

    async def create_tunnel(
        self,
        config: ConnectionConfig,
        username: str,
        connect: bool = True
    ) -> Tunnel:
        """
        Create a new tunnel.

        Args:
            config: Connection configuration
            username: OS user creating this tunnel
            connect: If True, automatically connect after creation

        Returns:
            Tunnel object
        """
        if not self.connected:
            raise DBusError("Not connected to D-Bus")

        iface = self.proxy.get_interface("org.protonvpn.Manager")

        config_dict = config.to_dict()
        dbus_dict = {k: _to_variant(v) for k, v in config_dict.items()}

        try:
            result_dict = await iface.call_create_tunnel(dbus_dict, username)
        except DNextBusError as e:
            raise DBusError(f"D-Bus error: {e}") from e

        # Convert back to Tunnel object (handle both Variant and raw values)
        tunnel_data = {k: (v.value if isinstance(v, Variant) else v) for k, v in result_dict.items()}
        return Tunnel.from_dict(tunnel_data)

    async def destroy_tunnel(self, name: str, username: str) -> bool:
        """Destroy a tunnel completely."""
        if not self.connected:
            raise DBusError("Not connected to D-Bus")
        iface = self.proxy.get_interface("org.protonvpn.Manager")
        return await iface.call_destroy_tunnel(name, username)

    async def connect_tunnel(self, name: str, username: str) -> bool:
        """Connect an existing tunnel."""
        if not self.connected:
            raise DBusError("Not connected to D-Bus")
        iface = self.proxy.get_interface("org.protonvpn.Manager")
        return await iface.call_connect_tunnel(name, username)

    async def disconnect_tunnel(self, name: str, username: str) -> bool:
        """Disconnect a tunnel."""
        if not self.connected:
            raise DBusError("Not connected to D-Bus")
        iface = self.proxy.get_interface("org.protonvpn.Manager")
        return await iface.call_disconnect_tunnel(name, username)

    async def list_tunnels(
        self,
        username: str,
        all_users: bool = False
    ) -> List[Tunnel]:
        """List tunnels."""
        if not self.connected:
            raise DBusError("Not connected to D-Bus")
        iface = self.proxy.get_interface("org.protonvpn.Manager")

        results = await iface.call_list_tunnels(username, all_users)
        tunnels = []
        for d in results:
            data = {k: (v.value if isinstance(v, Variant) else v) for k, v in d.items()}
            tunnels.append(Tunnel.from_dict(data))
        return tunnels

    async def get_tunnel(self, name: str, username: str) -> Optional[Tunnel]:
        """Get a specific tunnel by name."""
        tunnels = await self.list_tunnels(username)
        for tunnel in tunnels:
            if tunnel.name == name:
                return tunnel
        return None

    async def get_status(self, name: str, username: str) -> TunnelStatus:
        """Get status for a tunnel."""
        if not self.connected:
            raise DBusError("Not connected to D-Bus")
        iface = self.proxy.get_interface("org.protonvpn.Manager")

        result = await iface.call_get_tunnel_status(name, username)
        status_str = result.get("status", Variant("s", "unknown")).value
        return TunnelStatus(status_str)

    async def get_traffic_stats(
        self,
        name: str,
        username: str
    ) -> Tuple[int, int]:
        """Get traffic stats for a tunnel."""
        if not self.connected:
            raise DBusError("Not connected to D-Bus")
        iface = self.proxy.get_interface("org.protonvpn.Manager")

        bytes_in, bytes_out = await iface.call_get_traffic_stats(name, username)
        return (bytes_in, bytes_out)

    async def list_adapters(self) -> List[str]:
        """List registered adapter names."""
        if not self.connected:
            raise DBusError("Not connected to D-Bus")
        iface = self.proxy.get_interface("org.protonvpn.Manager")
        return await iface.call_list_adapters()

    async def get_adapter_capabilities(self, adapter: str) -> AdapterCapabilities:
        """Get capabilities for an adapter."""
        if not self.connected:
            raise DBusError("Not connected to D-Bus")
        iface = self.proxy.get_interface("org.protonvpn.Manager")

        result = await iface.call_get_adapter_capabilities(adapter)
        return AdapterCapabilities(
            multi_tunnel=result.get("multi_tunnel", Variant("b", False)).value,
            supports_protocols=result.get("supports_protocols", Variant("as", [])).value,
            max_tunnels=result.get("max_tunnels", Variant("i", -1)).value,
            supports_per_app_routing=result.get(
                "supports_per_app_routing", Variant("b", False)
            ).value,
            supports_kill_switch=result.get("supports_kill_switch", Variant("b", False)).value,
            supports_dns_isolation=result.get(
                "supports_dns_isolation", Variant("b", False)
            ).value,
        )

    async def ping(self) -> bool:
        """Health check: ping the daemon."""
        if not self.connected:
            return False
        try:
            iface = self.proxy.get_interface("org.protonvpn.Manager")
            return await iface.call_ping()
        except Exception:
            return False

    # Session management methods

    async def list_sessions(
        self,
        username: str,
        adapter: str = "",
        all_users: bool = False
    ) -> List[Dict[str, Any]]:
        """
        List available VPN sessions.

        Args:
            username: Requesting user
            adapter: Filter by adapter type
            all_users: If True, list all users' sessions (admin only)

        Returns:
            List of session info dictionaries
        """
        if not self.connected:
            raise DBusError("Not connected to D-Bus")
        iface = self.proxy.get_interface("org.protonvpn.Manager")

        results = await iface.call_list_sessions(username, adapter, all_users)
        sessions = []
        for d in results:
            data = {k: v.value for k, v in d.items()}
            sessions.append(data)
        return sessions

    async def login(
        self,
        adapter: str,
        session_name: str,
        username: str,
        password: str,
        twofa_code: str = ""
    ) -> Dict[str, Any]:
        """
        Create a new session by logging in.

        Args:
            adapter: Adapter type
            session_name: Desired session identifier
            username: VPN account username
            password: Account password
            twofa_code: Optional 2FA code

        Returns:
            Session info dictionary
        """
        if not self.connected:
            raise DBusError("Not connected to D-Bus")
        iface = self.proxy.get_interface("org.protonvpn.Manager")

        result = await iface.call_login(adapter, session_name, username, password, twofa_code)
        return {k: v.value for k, v in result.items()}

    async def logout(
        self,
        adapter: str,
        session_name: str,
        username: str
    ) -> bool:
        """
        Logout and remove a session.

        Args:
            adapter: Adapter type
            session_name: Session to remove
            username: User requesting logout

        Returns:
            True if successful
        """
        if not self.connected:
            raise DBusError("Not connected to D-Bus")
        iface = self.proxy.get_interface("org.protonvpn.Manager")
        return await iface.call_logout(adapter, session_name, username)

    # Signal handling (for future CLI features like real-time updates)

    async def listen_for_signals(self, callback):
        """
        Listen for TunnelStateChanged signals.

        Args:
            callback: async function(tunnel_name: str, state: str) -> None
        """
        if not self.connected:
            raise DBusError("Not connected to D-Bus")

        # This is simplified; production code should properly handle filters
        # and reconnections
        raise NotImplementedError("Signal listening not implemented yet")


# Convenience function
async def get_client() -> VPNManagerClient:
    """
    Create and connect a client.

    Returns:
        Connected VPNManagerClient
    """
    client = VPNManagerClient()
    await client.connect()
    return client
