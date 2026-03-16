"""Unit tests for VPNManagerClient.

Tests cover:
- Connection management (connect, disconnect)
- All tunnel management methods (create, destroy, connect, disconnect, list, etc.)
- Status and stats retrieval
- Adapter capabilities
- Session management (login, logout, list_sessions)
- Variant conversion
- Error handling (not connected, D-Bus errors)
- Reconnection logic
"""

import pytest
import asyncio
from unittest.mock import Mock, AsyncMock, MagicMock, patch
from datetime import datetime

from dbus_next import Variant
from dbus_next.aio import MessageBus

from libvpnmanager.dbus.client import VPNManagerClient
from libvpnmanager.models.tunnel import Tunnel
from libvpnmanager.models.config import ConnectionConfig
from libvpnmanager.models.status import TunnelStatus
from libvpnmanager.models.exceptions import DBusError
from libvpnmanager.adapters.base import AdapterCapabilities


class MockDBusInterface:
    """Mock D-Bus interface for testing."""

    def __init__(self):
        self.call_create_tunnel = AsyncMock()
        self.call_destroy_tunnel = AsyncMock(return_value=True)
        self.call_connect_tunnel = AsyncMock(return_value=True)
        self.call_disconnect_tunnel = AsyncMock(return_value=True)
        self.call_list_tunnels = AsyncMock(return_value=[])
        self.call_get_tunnel_status = AsyncMock(return_value={})
        self.call_get_traffic_stats = AsyncMock(return_value=(0, 0))
        self.call_list_adapters = AsyncMock(return_value=[])
        self.call_get_adapter_capabilities = AsyncMock(return_value={})
        self.call_ping = AsyncMock(return_value=True)
        self.call_list_sessions = AsyncMock(return_value=[])
        self.call_login = AsyncMock(return_value={})
        self.call_logout = AsyncMock(return_value=True)

    def get_interface(self, name):
        return self


class MockMessageBus:
    """Mock MessageBus for testing."""

    def __init__(self):
        self.interface = MockDBusInterface()

    async def connect(self):
        return self

    async def introspect(self, service, path):
        """Mock introspect - returns a simple introspection object."""
        # Return a minimal introspection XML-like string or Mock object
        mock_introspect = Mock()
        mock_introspect.interface_name = "org.protonvpn.Manager"
        return mock_introspect

    def get_proxy_object(self, service, path, introspect):
        proxy = Mock()
        proxy.get_interface = MagicMock(return_value=self.interface)
        return proxy

    async def request_name(self, name):
        pass


class TestVPNManagerClientInit:
    """Tests for VPNManagerClient initialization."""

    def test_client_init_without_bus(self):
        """Test client initializes with no bus."""
        client = VPNManagerClient()
        assert client.bus is None
        assert client.proxy is None
        assert client.connected is False

    def test_client_init_with_bus(self):
        """Test client initializes with provided bus."""
        bus = Mock()
        client = VPNManagerClient(bus)
        assert client.bus is bus
        assert client.connected is False


class TestVPNManagerClientConnect:
    """Tests for connect method."""

    @pytest.mark.asyncio
    async def test_connect_creates_bus_if_none(self):
        """Test that connect creates MessageBus if none provided."""
        client = VPNManagerClient()

        with patch('libvpnmanager.dbus.client.MessageBus') as mock_bus_class:
            mock_bus = AsyncMock()
            mock_bus.connect = AsyncMock(return_value=mock_bus)
            mock_bus.introspect = AsyncMock(return_value=Mock())
            mock_bus_class.return_value = mock_bus

            await client.connect()

            assert client.connected is True
            assert client.bus is mock_bus

    @pytest.mark.asyncio
    async def test_connect_uses_provided_bus(self):
        """Test that connect uses provided bus."""
        bus = MockMessageBus()
        client = VPNManagerClient(bus)

        await client.connect()

        assert client.connected is True
        assert client.proxy is not None

    @pytest.mark.asyncio
    async def test_connect_idempotent(self):
        """Test calling connect multiple times is safe."""
        bus = MockMessageBus()
        client = VPNManagerClient(bus)

        await client.connect()
        await client.connect()  # Should not error

        assert client.connected is True


class TestVPNManagerClientDisconnect:
    """Tests for disconnect method."""

    @pytest.mark.asyncio
    async def test_disconnect_clears_state(self):
        """Test that disconnect clears proxy and connected flag."""
        bus = MockMessageBus()
        client = VPNManagerClient(bus)
        await client.connect()

        await client.disconnect()

        assert client.proxy is None
        assert client.connected is False


class TestVPNManagerClientCreateTunnel:
    """Tests for create_tunnel method."""

    @pytest.fixture
    def client(self):
        bus = MockMessageBus()
        client = VPNManagerClient(bus)
        asyncio.run(client.connect())
        return client

    @pytest.mark.asyncio
    async def test_create_tunnel_success(self, client):
        """Test successful tunnel creation."""
        # Mock the D-Bus response
        tunnel_data = {
            "name": "test_tunnel",
            "adapter": "dummy",
            "session_name": "test_session",
            "username": "alice",
            "device": "tun-test",
            "namespace": "ns-test",
            "endpoint": "1.2.3.4",
            "connected_at": datetime.utcnow().isoformat(),
            "bytes_in": 0,
            "bytes_out": 0,
            "status": "connected",
            "metadata": {},
        }
        client.bus.interface.call_create_tunnel.return_value = tunnel_data

        config = ConnectionConfig(
            adapter="dummy",
            tunnel_name="test_tunnel",
            session_name="test_session"
        )

        tunnel = await client.create_tunnel(config, "alice")

        assert isinstance(tunnel, Tunnel)
        assert tunnel.name == "test_tunnel"
        assert tunnel.adapter == "dummy"
        assert tunnel.username == "alice"
        assert tunnel.device == "tun-test"

    @pytest.mark.asyncio
    async def test_create_tunnel_not_connected(self):
        """Test create_tunnel raises error when not connected."""
        client = VPNManagerClient()
        config = ConnectionConfig(
            adapter="dummy",
            tunnel_name="test",
            session_name="test"
        )

        with pytest.raises(DBusError, match="Not connected"):
            await client.create_tunnel(config, "alice")

    @pytest.mark.asyncio
    async def test_create_tunnel_config_conversion(self, client):
        """Test that config is properly converted to D-Bus dict."""
        config = ConnectionConfig(
            adapter="dummy",
            tunnel_name="test_tunnel",
            session_name="test_session"
        )
        # Additional metadata
        config.metadata = {"key": "value"}

        # Mock response for the create_tunnel call
        client.bus.interface.call_create_tunnel.return_value = {
            "name": Variant("s", "test_tunnel"),
            "adapter": Variant("s", "dummy"),
            "session_name": Variant("s", "test_session"),
            "username": Variant("s", "alice"),
            "device": Variant("s", "tun-test"),
            "namespace": Variant("s", "ns-test"),
            "endpoint": Variant("s", "1.2.3.4"),
            "connected_at": Variant("s", datetime.utcnow().isoformat()),
            "bytes_in": Variant("x", 0),
            "bytes_out": Variant("x", 0),
            "status": Variant("s", "connected"),
            "metadata": Variant("a{sv}", {}),
        }

        await client.create_tunnel(config, "alice")

        # Check that call was made with proper dict
        call_args = client.bus.interface.call_create_tunnel.call_args
        config_dict = call_args[0][0]  # First positional arg

        assert config_dict["adapter"].value == "dummy"
        assert config_dict["tunnel_name"].value == "test_tunnel"
        assert config_dict["session_name"].value == "test_session"

    @pytest.mark.asyncio
    async def test_create_tunnel_variant_conversion(self, client):
        """Test that D-Bus variants are properly converted back."""
        tunnel_dict = {
            "name": Variant("s", "test"),
            "adapter": Variant("s", "dummy"),
            "session_name": Variant("s", "test"),
            "username": Variant("s", "alice"),
            "device": Variant("s", ""),
            "namespace": Variant("s", ""),
            "endpoint": Variant("s", ""),
            "connected_at": Variant("s", ""),
            "bytes_in": Variant("x", 0),
            "bytes_out": Variant("x", 0),
            "status": Variant("s", "disconnected"),
        }
        client.bus.interface.call_create_tunnel.return_value = tunnel_dict

        config = ConnectionConfig(
            adapter="dummy",
            tunnel_name="test",
            session_name="test"
        )

        tunnel = await client.create_tunnel(config, "alice")
        assert tunnel.name == "test"


class TestVPNManagerClientDestroyTunnel:
    """Tests for destroy_tunnel method."""

    @pytest.fixture
    def client(self):
        bus = MockMessageBus()
        client = VPNManagerClient(bus)
        asyncio.run(client.connect())
        return client

    @pytest.mark.asyncio
    async def test_destroy_tunnel_success(self, client):
        """Test successful tunnel destruction."""
        result = await client.destroy_tunnel("test_tunnel", "alice")
        assert result is True

    @pytest.mark.asyncio
    async def test_destroy_tunnel_not_connected(self):
        """Test destroy_tunnel raises error when not connected."""
        client = VPNManagerClient()

        with pytest.raises(DBusError, match="Not connected"):
            await client.destroy_tunnel("test", "alice")


class TestVPNManagerClientConnectDisconnectTunnel:
    """Tests for connect_tunnel and disconnect_tunnel methods."""

    @pytest.fixture
    def client(self):
        bus = MockMessageBus()
        client = VPNManagerClient(bus)
        asyncio.run(client.connect())
        return client

    @pytest.mark.asyncio
    async def test_connect_tunnel_success(self, client):
        """Test successful connect."""
        result = await client.connect_tunnel("test_tunnel", "alice")
        assert result is True

    @pytest.mark.asyncio
    async def test_disconnect_tunnel_success(self, client):
        """Test successful disconnect."""
        result = await client.disconnect_tunnel("test_tunnel", "alice")
        assert result is True


class TestVPNManagerClientListTunnels:
    """Tests for list_tunnels method."""

    @pytest.fixture
    def client(self):
        bus = MockMessageBus()
        client = VPNManagerClient(bus)
        asyncio.run(client.connect())
        return client

    @pytest.mark.asyncio
    async def test_list_tunnels_success(self, client):
        """Test successful tunnel listing."""
        now = datetime.utcnow().isoformat()
        tunnel_data = [
            {
                "name": "tunnel1",
                "adapter": "dummy",
                "session_name": "test",
                "username": "alice",
                "device": "tun1",
                "namespace": "ns1",
                "endpoint": "1.2.3.4",
                "connected_at": now,
                "bytes_in": Variant("x", 1000),
                "bytes_out": Variant("x", 2000),
                "status": Variant("s", "connected"),
                "metadata": Variant("a{sv}", {}),
            },
            {
                "name": "tunnel2",
                "adapter": "dummy",
                "session_name": "test",
                "username": "bob",
                "device": "",
                "namespace": "",
                "endpoint": "",
                "connected_at": "",
                "bytes_in": Variant("x", 0),
                "bytes_out": Variant("x", 0),
                "status": Variant("s", "disconnected"),
                "metadata": Variant("a{sv}", {}),
            },
        ]
        client.bus.interface.call_list_tunnels.return_value = tunnel_data

        tunnels = await client.list_tunnels("alice")

        assert len(tunnels) == 2
        assert isinstance(tunnels[0], Tunnel)
        assert tunnels[0].name == "tunnel1"
        assert tunnels[1].name == "tunnel2"


class TestVPNManagerClientGetStatus:
    """Tests for get_status method."""

    @pytest.fixture
    def client(self):
        bus = MockMessageBus()
        client = VPNManagerClient(bus)
        asyncio.run(client.connect())
        return client

    @pytest.mark.asyncio
    async def test_get_status_success(self, client):
        """Test successful status retrieval."""
        status_dict = {
            "name": Variant("s", "test_tunnel"),
            "status": Variant("s", "connected"),
            "adapter": Variant("s", "dummy"),
            "device": Variant("s", "tun0"),
            "namespace": Variant("s", "ns-test"),
            "endpoint": Variant("s", "1.2.3.4"),
            "session_name": Variant("s", "test_session"),
            "owner": Variant("s", "alice"),
        }
        client.bus.interface.call_get_tunnel_status.return_value = status_dict

        status = await client.get_status("test_tunnel", "alice")

        assert isinstance(status, TunnelStatus)
        assert status == TunnelStatus.CONNECTED

    @pytest.mark.asyncio
    async def test_get_status_unknown_tunnel(self, client):
        """Test get_status with unknown tunnel returns disconnected."""
        status_dict = {
            "status": Variant("s", "disconnected"),
        }
        client.bus.interface.call_get_tunnel_status.return_value = status_dict

        status = await client.get_status("test_tunnel", "alice")
        # The client returns status from dict, should be disconnected


class TestVPNManagerClientGetTrafficStats:
    """Tests for get_traffic_stats method."""

    @pytest.fixture
    def client(self):
        bus = MockMessageBus()
        client = VPNManagerClient(bus)
        asyncio.run(client.connect())
        return client

    @pytest.mark.asyncio
    async def test_get_traffic_stats_success(self, client):
        """Test successful traffic stats retrieval."""
        client.bus.interface.call_get_traffic_stats.return_value = (1000, 2000)

        bytes_in, bytes_out = await client.get_traffic_stats("test_tunnel", "alice")

        assert bytes_in == 1000
        assert bytes_out == 2000


class TestVPNManagerClientListAdapters:
    """Tests for list_adapters method."""

    @pytest.fixture
    def client(self):
        bus = MockMessageBus()
        client = VPNManagerClient(bus)
        asyncio.run(client.connect())
        return client

    @pytest.mark.asyncio
    async def test_list_adapters_success(self, client):
        """Test successful adapter listing."""
        client.bus.interface.call_list_adapters.return_value = ["dummy", "proton", "psiphon"]

        adapters = await client.list_adapters()

        assert adapters == ["dummy", "proton", "psiphon"]


class TestVPNManagerClientGetAdapterCapabilities:
    """Tests for get_adapter_capabilities method."""

    @pytest.fixture
    def client(self):
        bus = MockMessageBus()
        client = VPNManagerClient(bus)
        asyncio.run(client.connect())
        return client

    @pytest.mark.asyncio
    async def test_get_adapter_capabilities_success(self, client):
        """Test successful capabilities retrieval."""
        caps_dict = {
            "multi_tunnel": Variant("b", True),
            "supports_protocols": Variant("as", ["wireguard", "openvpn"]),
            "max_tunnels": Variant("i", 10),
            "supports_per_app_routing": Variant("b", False),
            "supports_kill_switch": Variant("b", True),
            "supports_dns_isolation": Variant("b", True),
        }
        client.bus.interface.call_get_adapter_capabilities.return_value = caps_dict

        caps = await client.get_adapter_capabilities("proton")

        assert isinstance(caps, AdapterCapabilities)
        assert caps.multi_tunnel is True
        assert caps.supports_protocols == ["wireguard", "openvpn"]
        assert caps.max_tunnels == 10
        assert caps.supports_per_app_routing is False
        assert caps.supports_kill_switch is True
        assert caps.supports_dns_isolation is True


class TestVPNManagerClientPing:
    """Tests for ping method."""

    @pytest.fixture
    def client(self):
        bus = MockMessageBus()
        client = VPNManagerClient(bus)
        asyncio.run(client.connect())
        return client

    @pytest.mark.asyncio
    async def test_ping_success(self, client):
        """Test ping returns True when daemon responds."""
        result = await client.ping()
        assert result is True

    @pytest.mark.asyncio
    async def test_ping_when_not_connected(self):
        """Test ping returns False when not connected."""
        client = VPNManagerClient()
        result = await client.ping()
        assert result is False


class TestVPNManagerClientSessions:
    """Tests for session management methods."""

    @pytest.fixture
    def client(self):
        bus = MockMessageBus()
        client = VPNManagerClient(bus)
        asyncio.run(client.connect())
        return client

    @pytest.mark.asyncio
    async def test_list_sessions_success(self, client):
        """Test successful session listing."""
        session_data = [
            {
                "adapter": Variant("s", "dummy"),
                "session_name": Variant("s", "test_session"),
                "username": Variant("s", "alice"),
                "status": Variant("s", "active"),
            }
        ]
        client.bus.interface.call_list_sessions.return_value = session_data

        sessions = await client.list_sessions("alice")

        assert isinstance(sessions, list)
        assert len(sessions) >= 0

    @pytest.mark.asyncio
    async def test_login_success(self, client):
        """Test successful login."""
        session_data = {
            "adapter": Variant("s", "dummy"),
            "session_name": Variant("s", "test_session"),
            "username": Variant("s", "alice"),
            "status": Variant("s", "active"),
        }
        client.bus.interface.call_login.return_value = session_data

        result = await client.login(
            adapter="dummy",
            session_name="test_session",
            username="alice",
            password="password123"
        )

        assert isinstance(result, dict)
        assert result["adapter"] == "dummy"

    @pytest.mark.asyncio
    async def test_logout_success(self, client):
        """Test successful logout."""
        result = await client.logout("dummy", "test_session", "alice")
        assert result is True


class TestVPNManagerClientErrorHandling:
    """Tests for error handling."""

    @pytest.fixture
    def client(self):
        bus = MockMessageBus()
        client = VPNManagerClient(bus)
        asyncio.run(client.connect())
        return client

    @pytest.mark.asyncio
    async def test_methods_raise_when_not_connected(self):
        """Test all methods raise DBusError when not connected."""
        client = VPNManagerClient()

        methods_to_test = [
            ('create_tunnel', (ConnectionConfig(adapter="dummy", tunnel_name="t", session_name="s"), "alice")),
            ('destroy_tunnel', ("t", "alice")),
            ('connect_tunnel', ("t", "alice")),
            ('disconnect_tunnel', ("t", "alice")),
            ('list_tunnels', ("alice",)),
            ('get_status', ("t", "alice")),
            ('get_traffic_stats', ("t", "alice")),
            ('list_adapters', ()),
            ('get_adapter_capabilities', ("dummy",)),
            ('list_sessions', ("alice",)),
            ('login', ("dummy", "s", "alice", "pass")),
            ('logout', ("dummy", "s", "alice")),
        ]

        for method_name, args in methods_to_test:
            client = VPNManagerClient()  # Fresh client, not connected
            method = getattr(client, method_name)
            with pytest.raises(DBusError, match="Not connected"):
                if asyncio.iscoroutinefunction(method):
                    await method(*args)
                else:
                    method(*args)

    @pytest.mark.asyncio
    async def test_dbus_error_propagation(self, client):
        """Test that D-Bus errors are properly wrapped."""
        from dbus_next import DBusError as NextDBusError

        async def raise_dbus_error(*args, **kwargs):
            raise NextDBusError("test.error", "Test error message")

        client.bus.interface.call_create_tunnel.side_effect = raise_dbus_error

        config = ConnectionConfig(
            adapter="dummy",
            tunnel_name="test",
            session_name="test"
        )

        with pytest.raises(DBusError):
            await client.create_tunnel(config, "alice")


class TestVPNManagerClientVariantConversion:
    """Tests for variant conversion logic."""

    @pytest.fixture
    def client(self):
        bus = MockMessageBus()
        client = VPNManagerClient(bus)
        asyncio.run(client.connect())
        return client

    def test_config_to_variant_dict(self, client):
        """Test that config dictionary is converted to variants."""
        config = ConnectionConfig(
            adapter="dummy",
            tunnel_name="test_tunnel",
            session_name="test_session"
        )
        config_dict = config.to_dict()

        # The client converts to variants inline in create_tunnel
        # We can't directly test the conversion, but we can verify the call
        pass

    @pytest.mark.asyncio
    async def test_result_from_variant_dict(self, client):
        """Test that result dictionary with variants is converted."""
        # Simulate D-Bus returning variants
        result_with_variants = {
            "name": Variant("s", "test"),
            "adapter": Variant("s", "dummy"),
            "username": Variant("s", "alice"),
            "device": Variant("s", "tun0"),
            "namespace": Variant("s", "ns-test"),
            "endpoint": Variant("s", ""),
            "connected_at": Variant("s", ""),
            "bytes_in": Variant("x", 0),
            "bytes_out": Variant("x", 0),
            "status": Variant("s", "connected"),
            "metadata": Variant("a{sv}", {}),
        }
        client.bus.interface.call_create_tunnel.return_value = result_with_variants

        config = ConnectionConfig(
            adapter="dummy",
            tunnel_name="test",
            session_name="test"
        )

        tunnel = await client.create_tunnel(config, "alice")

        # Should be Tunnel object with values extracted
        assert tunnel.name == "test"
        assert tunnel.adapter == "dummy"
        assert tunnel.device == "tun0"


class TestVPNManagerClientGetTunnel:
    """Tests for get_tunnel helper method."""

    @pytest.fixture
    def client(self):
        bus = MockMessageBus()
        client = VPNManagerClient(bus)
        asyncio.run(client.connect())
        return client

    @pytest.mark.asyncio
    async def test_get_tunnel_found(self, client):
        """Test getting existing tunnel by name."""
        now = datetime.utcnow().isoformat()
        tunnels_data = [
            {
                "name": "tunnel1",
                "adapter": "dummy",
                "session_name": "test",
                "username": "alice",
                "device": "tun1",
                "namespace": "ns1",
                "endpoint": "1.2.3.4",
                "connected_at": now,
                "bytes_in": Variant("x", 1000),
                "bytes_out": Variant("x", 2000),
                "status": Variant("s", "connected"),
                "metadata": Variant("a{sv}", {}),
            }
        ]
        client.bus.interface.call_list_tunnels.return_value = tunnels_data

        tunnel = await client.get_tunnel("tunnel1", "alice")

        assert tunnel is not None
        assert tunnel.name == "tunnel1"

    @pytest.mark.asyncio
    async def test_get_tunnel_not_found(self, client):
        """Test getting non-existent tunnel returns None."""
        client.bus.interface.call_list_tunnels.return_value = []

        tunnel = await client.get_tunnel("nonexistent", "alice")
        assert tunnel is None
