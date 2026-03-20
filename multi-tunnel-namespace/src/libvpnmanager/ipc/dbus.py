"""D-Bus IPC transport.

Wraps the existing libvpnmanager D-Bus service (ManagerService) and client (VPNManagerClient)
to conform to the IPCTransport abstraction.

This transport uses the system D-Bus and requires dbus_next.
"""

from typing import Any, Dict, Optional, Callable, Awaitable
from ..models.exceptions import VPNManagerError

from .transport import (
    IPCTransport, IPCServer, IPCClient, Message, MessageType, TransportConfig, IPCError, register_transport
)

try:
    from ..dbus.service import ManagerService, start_service as dbus_start_service
    from ..dbus.client import VPNManagerClient as DBusVPNManagerClient
    DBT_AVAILABLE = True
except ImportError:
    DBT_AVAILABLE = False
    ManagerService = None
    dbus_start_service = None
    DBusVPNManagerClient = None


class DBusServer(IPCServer):
    """D-Bus server wrapper.

    Exposes the TunnelManager via D-Bus on the system bus.
    """

    def __init__(self, manager: Any, config: TransportConfig):
        if not DBT_AVAILABLE:
            raise IPCError("dbus_next not available")
        super().__init__(manager)
        self.config = config
        self._bus = None
        self._service = None

    async def start(self) -> None:
        """Start D-Bus service."""
        self._bus, self._service = await dbus_start_service(self.manager)

    async def stop(self) -> None:
        """Stop D-Bus service."""
        if self._bus:
            try:
                self._bus.disconnect()
            except:
                pass
            self._bus = None
            self._service = None

    async def emit_signal(self, signal: str, data: Dict[str, Any]) -> None:
        """Emit a D-Bus signal."""
        if not self._service:
            raise IPCError("D-Bus service not running")
        # The ManagerService has signal methods like TunnelStateChanged(name, state)
        # We need to map generic signal emission to specific D-Bus signal calls.
        if signal == "TunnelStateChanged":
            self._service.TunnelStateChanged(
                data.get("name", ""),
                data.get("state", "")
            )
        elif signal == "TunnelCreated":
            self._service.TunnelCreated(data.get("name", ""))
        elif signal == "TunnelDestroyed":
            self._service.TunnelDestroyed(data.get("name", ""))
        elif signal == "AdapterRegistered":
            self._service.AdapterRegistered(
                data.get("adapter_type", ""),
                data.get("version", "")
            )
        else:
            # Unknown signal - ignore or log
            pass


class DBusClient(IPCClient):
    """D-Bus client wrapper.

    Uses the existing VPNManagerClient to call methods over D-Bus.
    """

    def __init__(self, config: TransportConfig):
        if not DBT_AVAILABLE:
            raise IPCError("dbus_next not available")
        super().__init__()
        self.config = config
        self._client: Optional[DBusVPNManagerClient] = None

    async def connect(self) -> None:
        """Connect to D-Bus service."""
        self._client = DBusVPNManagerClient()
        await self._client.connect()
        self.connected = True

    async def disconnect(self) -> None:
        """Disconnect from D-Bus."""
        if self._client:
            await self._client.disconnect()
            self._client = None
        self.connected = False

    async def call_method(
        self,
        method: str,
        params: Optional[Dict[str, Any]] = None
    ) -> Any:
        """Call a method via D-Bus."""
        if not self._client:
            raise IPCError("Not connected")

        # Map method names to VPNManagerClient methods
        client_methods = {
            'CreateTunnel': self._client.create_tunnel,
            'DestroyTunnel': self._client.destroy_tunnel,
            'ConnectTunnel': self._client.connect_tunnel,
            'DisconnectTunnel': self._client.disconnect_tunnel,
            'ListTunnels': self._client.list_tunnels,
            'GetTunnelStatus': self._client.get_status,
            'GetTrafficStats': self._client.get_traffic_stats,
            'ListAdapters': self._client.list_adapters,
            'GetAdapterCapabilities': self._client.get_adapter_capabilities,
            'Ping': self._client.ping,
            'ListSessions': self._client.list_sessions,
            'Login': self._client.login,
            'Logout': self._client.logout,
        }

        if method not in client_methods:
            raise IPCError(f"Unknown method: {method}")

        func = client_methods[method]
        # The client methods have different signatures; we need to adapt
        # E.g., create_tunnel takes config (ConnectionConfig object) and username
        # But our IPC passes params dict. So we need to convert.
        # This is a simplified version; in practice, we'd need proper mapping.

        # Quick mapping by parameter count seems fragile.
        # Instead, we rely on the fact that the client methods are designed
        # to be called with specific params. We'll just pass params as kwargs.
        try:
            result = await func(**params) if params else await func()
            # Convert result objects to dict if needed
            if hasattr(result, 'to_dict'):
                return result.to_dict()
            return result
        except Exception as e:
            raise IPCError(str(e))

    async def subscribe_signal(
        self,
        signal: str,
        callback: Callable[[Dict[str, Any]], Awaitable[None]]
    ) -> None:
        """Subscribe to D-Bus signals."""
        # Not implemented in current client
        raise NotImplementedError("Signal subscription not implemented in D-Bus client")

# Register this transport (after class definitions)
register_transport('dbus', DBusServer, DBusClient)
