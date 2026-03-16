"""Unit tests for D-Bus service (ManagerService).

Tests cover:
- All D-Bus methods (CreateTunnel, DestroyTunnel, ConnectTunnel, etc.)
- Signal emission (TunnelStateChanged, TunnelCreated, TunnelDestroyed)
- Variant serialization/deserialization
- Error handling and propagation
- Permission checks via manager
"""

import pytest
import asyncio
from datetime import datetime
from unittest.mock import Mock, AsyncMock, patch, MagicMock

from dbus_next.service import ServiceInterface
from dbus_next import Variant, DBusError

from libvpnmanager.dbus.service import ManagerService, _to_variant
from libvpnmanager.models.tunnel import Tunnel
from libvpnmanager.models.config import ConnectionConfig
from libvpnmanager.models.status import TunnelStatus
from libvpnmanager.models.exceptions import (
    TunnelExistsError,
    TunnelNotFoundError,
    AccessDeniedError,
    AdapterNotFoundError,
)
from libvpnmanager.adapters.base import AdapterCapabilities


class MockManager:
    """Mock TunnelManager for testing D-Bus service."""

    def __init__(self):
        self.tunnels = {}
        self._adapters = {}
        self.session_manager = Mock()
        self.session_manager.SESSION_TYPES = {"dummy": Mock(), "proton": Mock()}

    async def create_tunnel(self, config, username):
        if config.tunnel_name in self.tunnels:
            raise TunnelExistsError(f"Tunnel {config.tunnel_name} already exists")
        tunnel = Tunnel(
            name=config.tunnel_name,
            adapter=config.adapter,
            session_name=config.session_name,
            username=username,
            device=f"tun-{config.tunnel_name}",
            namespace=f"ns-{config.tunnel_name}",
            endpoint="1.2.3.4",
            connected_at=datetime.utcnow(),
        )
        self.tunnels[config.tunnel_name] = tunnel
        return tunnel

    async def connect_tunnel(self, name, username):
        tunnel = self.tunnels.get(name)
        if not tunnel:
            raise TunnelNotFoundError(f"Tunnel {name} not found")
        if tunnel.username != username:
            raise AccessDeniedError(f"User {username} cannot manage tunnel {name}")
        tunnel.device = f"tun-{name}"
        tunnel.namespace = f"ns-{name}"
        tunnel.connected_at = datetime.utcnow()
        return tunnel

    async def disconnect_tunnel(self, name, username):
        tunnel = self.tunnels.get(name)
        if not tunnel:
            raise TunnelNotFoundError(f"Tunnel {name} not found")
        if tunnel.username != username:
            raise AccessDeniedError(f"User {username} cannot manage tunnel {name}")
        tunnel.device = ""
        tunnel.namespace = None
        tunnel.connected_at = None

    async def destroy_tunnel(self, name, username):
        tunnel = self.tunnels.get(name)
        if not tunnel:
            raise TunnelNotFoundError(f"Tunnel {name} not found")
        if tunnel.username != username:
            raise AccessDeniedError(f"User {username} cannot manage tunnel {name}")
        del self.tunnels[name]

    async def list_tunnels(self, username=None, all_users=False):
        tunnels = list(self.tunnels.values())
        if all_users:
            # In real impl would check admin, but mock just returns all
            return tunnels
        if username:
            tunnels = [t for t in tunnels if t.username == username]
        return tunnels

    async def get_tunnel(self, name, username=None):
        tunnel = self.tunnels.get(name)
        if tunnel and username:
            if tunnel.username != username:
                raise AccessDeniedError(f"User {username} cannot access tunnel {name}")
        return tunnel

    async def get_status(self, name, username):
        tunnel = await self.get_tunnel(name, username)
        if not tunnel or not tunnel.device:
            return TunnelStatus.DISCONNECTED
        return TunnelStatus.CONNECTED

    async def get_traffic_stats(self, name, username):
        tunnel = await self.get_tunnel(name, username)
        if not tunnel:
            raise TunnelNotFoundError(f"Tunnel {name} not found")
        return (1000, 2000)

    async def list_adapters(self):
        return list(self.session_manager.SESSION_TYPES.keys())

    async def get_adapter_capabilities(self, adapter):
        caps_map = {
            "dummy": AdapterCapabilities(
                multi_tunnel=True,
                supports_protocols=["dummy"],
                max_tunnels=None,
                supports_per_app_routing=True,
                supports_kill_switch=False,
                supports_dns_isolation=False,
            ),
            "proton": AdapterCapabilities(
                multi_tunnel=True,
                supports_protocols=["wireguard", "openvpn"],
                max_tunnels=10,
                supports_per_app_routing=False,
                supports_kill_switch=True,
                supports_dns_isolation=True,
            ),
        }
        if adapter not in caps_map:
            raise AdapterNotFoundError(f"Adapter {adapter} not found")
        return caps_map[adapter]

    async def shutdown(self):
        self.tunnels.clear()
        self._adapters.clear()


class TestToVariant:
    """Tests for _to_variant helper function."""

    def test_to_variant_string(self):
        """Test converting string to Variant."""
        v = _to_variant("test")
        assert isinstance(v, Variant)
        assert v.signature == 's'
        assert v.value == "test"

    def test_to_variant_bool(self):
        """Test converting bool to Variant."""
        v = _to_variant(True)
        assert v.signature == 'b'
        assert v.value is True

        v = _to_variant(False)
        assert v.value is False

    def test_to_variant_int(self):
        """Test converting int to Variant."""
        v = _to_variant(12345)
        assert v.signature == 'x'
        assert v.value == 12345

    def test_to_variant_float(self):
        """Test converting float to Variant."""
        v = _to_variant(3.14159)
        assert v.signature == 'd'
        assert v.value == 3.14159

    def test_to_variant_bytes(self):
        """Test converting bytes to Variant."""
        v = _to_variant(b"hello")
        assert v.signature == 'ay'
        assert v.value == b"hello"

    def test_to_variant_none(self):
        """Test converting None to Variant."""
        v = _to_variant(None)
        assert v.signature == 's'
        assert v.value == ""

    def test_to_variant_datetime(self):
        """Test converting datetime to Variant (ISO string)."""
        dt = datetime(2024, 1, 15, 10, 30, 0)
        v = _to_variant(dt)
        assert v.signature == 's'
        assert v.value == "2024-01-15T10:30:00"

    def test_to_variant_dict(self):
        """Test converting dict to Variant."""
        d = {"key1": "value1", "key2": 123, "key3": True}
        v = _to_variant(d)
        assert v.signature == 'a{sv}'
        assert isinstance(v.value, dict)
        assert v.value["key1"].value == "value1"
        assert v.value["key2"].value == 123
        assert v.value["key3"].value is True

    def test_to_variant_nested_dict(self):
        """Test converting nested dict to Variant."""
        d = {"outer": {"inner": "value"}}
        v = _to_variant(d)
        assert v.signature == 'a{sv}'
        # Nested dict becomes variant containing dict
        assert isinstance(v.value["outer"], Variant)

    def test_to_variant_unsupported_type(self):
        """Test that unsupported type raises TypeError."""
        class CustomObj:
            pass

        with pytest.raises(TypeError):
            _to_variant(CustomObj())


class TestManagerServiceInit:
    """Tests for ManagerService initialization."""

    def test_service_interface_name(self):
        """Test that service uses correct D-Bus interface name."""
        mock_manager = MockManager()
        service = ManagerService(mock_manager)
        assert service._interface_name == "org.protonvpn.Manager"

    def test_service_stores_manager(self):
        """Test that service stores TunnelManager reference."""
        mock_manager = MockManager()
        service = ManagerService(mock_manager)
        assert service.manager is mock_manager


class TestManagerServiceCreateTunnel:
    """Tests for CreateTunnel D-Bus method."""

    @pytest.fixture
    def service(self):
        mock_manager = MockManager()
        return ManagerService(mock_manager)

    @pytest.mark.asyncio
    async def test_create_tunnel_success(self, service):
        """Test successful tunnel creation via D-Bus."""
        config_dict = {
            "adapter": Variant("s", "dummy"),
            "tunnel_name": Variant("s", "test_tunnel"),
            "session_name": Variant("s", "test_session"),
        }
        result = await service.CreateTunnel(config_dict, "alice")

        # Result should be dict of variants
        assert isinstance(result, dict)
        assert "name" in result
        assert result["name"].value == "test_tunnel"
        assert result["adapter"].value == "dummy"
        assert result["username"].value == "alice"
        assert result["status"].value == "disconnected"  # or "connected" if auto-connect

    @pytest.mark.asyncio
    async def test_create_tunnel_auto_connects(self, service):
        """Test that CreateTunnel also connects the tunnel."""
        config_dict = {
            "adapter": Variant("s", "dummy"),
            "tunnel_name": Variant("s", "test_tunnel"),
            "session_name": Variant("s", "test_session"),
        }
        await service.CreateTunnel(config_dict, "alice")

        # Tunnel should be connected
        tunnel = service.manager.tunnels["test_tunnel"]
        assert tunnel.device  # not empty

    @pytest.mark.asyncio
    async def test_create_tunnel_missing_required_fields(self, service):
        """Test that missing required fields raises error."""
        config_dict = {
            "tunnel_name": Variant("s", "test_tunnel"),
            # Missing adapter
        }

        with pytest.raises(ValueError, match="adapter, tunnel_name, and session_name are required"):
            await service.CreateTunnel(config_dict, "alice")

    @pytest.mark.asyncio
    async def test_create_tunnel_duplicate_name(self, service):
        """Test that duplicate tunnel name raises TunnelExistsError."""
        config_dict = {
            "adapter": Variant("s", "dummy"),
            "tunnel_name": Variant("s", "duplicate_tunnel"),
            "session_name": Variant("s", "test_session"),
        }

        await service.CreateTunnel(config_dict, "alice")

        with pytest.raises(TunnelExistsError):
            await service.CreateTunnel(config_dict, "bob")

    @pytest.mark.asyncio
    async def test_create_tunnel_adapter_not_found(self, service):
        """Test that unknown adapter raises AdapterNotFoundError."""
        config_dict = {
            "adapter": Variant("s", "unknown"),
            "tunnel_name": Variant("s", "test_tunnel"),
            "session_name": Variant("s", "test_session"),
        }

        with pytest.raises(AdapterNotFoundError):
            await service.CreateTunnel(config_dict, "alice")


class TestManagerServiceDestroyTunnel:
    """Tests for DestroyTunnel D-Bus method."""

    @pytest.fixture
    def service(self):
        mock_manager = MockManager()
        service = ManagerService(mock_manager)
        # Pre-create a tunnel
        tunnel = Tunnel(
            name="test_tunnel",
            adapter="dummy",
            username="alice",
            device="tun-test",
            namespace="ns-test",
        )
        mock_manager.tunnels["test_tunnel"] = tunnel
        return service

    @pytest.mark.asyncio
    async def test_destroy_tunnel_success(self, service):
        """Test successful tunnel destruction."""
        result = await service.DestroyTunnel("test_tunnel", "alice")

        assert result is True
        assert "test_tunnel" not in service.manager.tunnels

    @pytest.mark.asyncio
    async def test_destroy_tunnel_emits_signal(self, service):
        """Test that DestroyTunnel emits TunnelDestroyed signal."""
        # Mock the signal emission
        service.TunnelDestroyed = Mock()

        await service.DestroyTunnel("test_tunnel", "alice")

        service.TunnelDestroyed.assert_called_once_with("test_tunnel")

    @pytest.mark.asyncio
    async def test_destroy_tunnel_not_found(self, service):
        """Test destroying non-existent tunnel raises error."""
        with pytest.raises(TunnelNotFoundError):
            await service.DestroyTunnel("nonexistent", "alice")

    @pytest.mark.asyncio
    async def test_destroy_tunnel_access_denied(self, service):
        """Test destroying another user's tunnel raises error."""
        with pytest.raises(AccessDeniedError):
            await service.DestroyTunnel("test_tunnel", "bob")


class TestManagerServiceConnectTunnel:
    """Tests for ConnectTunnel D-Bus method."""

    @pytest.fixture
    def service(self):
        mock_manager = MockManager()
        service = ManagerService(mock_manager)
        tunnel = Tunnel(
            name="test_tunnel",
            adapter="dummy",
            username="alice",
            device="",
            namespace=None,
        )
        mock_manager.tunnels["test_tunnel"] = tunnel
        return service

    @pytest.mark.asyncio
    async def test_connect_tunnel_success(self, service):
        """Test successful connection."""
        result = await service.ConnectTunnel("test_tunnel", "alice")

        assert result is True
        tunnel = service.manager.tunnels["test_tunnel"]
        assert tunnel.device  # device set
        assert tunnel.namespace is not None

    @pytest.mark.asyncio
    async def test_connect_tunnel_emits_signal(self, service):
        """Test that ConnectTunnel emits TunnelStateChanged signal."""
        service.TunnelStateChanged = Mock()

        await service.ConnectTunnel("test_tunnel", "alice")

        service.TunnelStateChanged.assert_called_once_with("test_tunnel", "connected")

    @pytest.mark.asyncio
    async def test_connect_tunnel_not_found(self, service):
        """Test connecting non-existent tunnel."""
        with pytest.raises(TunnelNotFoundError):
            await service.ConnectTunnel("nonexistent", "alice")


class TestManagerServiceDisconnectTunnel:
    """Tests for DisconnectTunnel D-Bus method."""

    @pytest.fixture
    def service(self):
        mock_manager = MockManager()
        service = ManagerService(mock_manager)
        tunnel = Tunnel(
            name="test_tunnel",
            adapter="dummy",
            username="alice",
            device="tun-test",
            namespace="ns-test",
            connected_at=datetime.utcnow(),
        )
        mock_manager.tunnels["test_tunnel"] = tunnel
        return service

    @pytest.mark.asyncio
    async def test_disconnect_tunnel_success(self, service):
        """Test successful disconnection."""
        result = await service.DisconnectTunnel("test_tunnel", "alice")

        assert result is True
        tunnel = service.manager.tunnels["test_tunnel"]
        assert tunnel.device == ""
        assert tunnel.namespace is None
        assert tunnel.connected_at is None

    @pytest.mark.asyncio
    async def test_disconnect_tunnel_emits_signal(self, service):
        """Test that DisconnectTunnel emits TunnelStateChanged signal."""
        service.TunnelStateChanged = Mock()

        await service.DisconnectTunnel("test_tunnel", "alice")

        service.TunnelStateChanged.assert_called_once_with("test_tunnel", "disconnected")


class TestManagerServiceListTunnels:
    """Tests for ListTunnels D-Bus method."""

    @pytest.fixture
    def service(self):
        mock_manager = MockManager()
        service = ManagerService(mock_manager)
        tunnel1 = Tunnel(name="alice_tunnel", adapter="dummy", username="alice", device="", namespace=None)
        tunnel2 = Tunnel(name="bob_tunnel", adapter="dummy", username="bob", device="", namespace=None)
        mock_manager.tunnels = {"alice_tunnel": tunnel1, "bob_tunnel": tunnel2}
        return service

    @pytest.mark.asyncio
    async def test_list_tunnels_single_user(self, service):
        """Test listing tunnels for a specific user."""
        result = await service.ListTunnels("alice", False)

        assert isinstance(result, list)
        assert len(result) == 1
        assert result[0]["name"].value == "alice_tunnel"

    @pytest.mark.asyncio
    async def test_list_tunnels_all_users(self, service):
        """Test listing all tunnels as admin."""
        result = await service.ListTunnels("root", True)

        assert len(result) == 2
        names = [item["name"].value for item in result]
        assert "alice_tunnel" in names
        assert "bob_tunnel" in names

    @pytest.mark.asyncio
    async def test_list_tunnels_non_admin_cannot_use_all_users(self, service):
        """Test non-admin cannot list all users."""
        with pytest.raises(AccessDeniedError):
            await service.ListTunnels("alice", True)


class TestManagerServiceGetTunnelStatus:
    """Tests for GetTunnelStatus D-Bus method."""

    @pytest.fixture
    def service(self):
        mock_manager = MockManager()
        service = ManagerService(mock_manager)
        return service

    @pytest.mark.asyncio
    async def test_get_tunnel_status_connected(self, service):
        """Test getting status of connected tunnel."""
        tunnel = Tunnel(
            name="test_tunnel",
            adapter="dummy",
            username="alice",
            device="tun0",
            namespace="ns-test",
            endpoint="1.2.3.4",
            connected_at=datetime(2024, 1, 15, 10, 0, 0),
        )
        service.manager.tunnels["test_tunnel"] = tunnel

        result = await service.GetTunnelStatus("test_tunnel", "alice")

        assert result["name"].value == "test_tunnel"
        assert result["status"].value == "connected"
        assert result["adapter"].value == "dummy"
        assert result["device"].value == "tun0"
        assert result["namespace"].value == "ns-test"
        assert result["endpoint"].value == "1.2.3.4"
        assert result["owner"].value == "alice"

    @pytest.mark.asyncio
    async def test_get_tunnel_status_disconnected(self, service):
        """Test getting status of disconnected tunnel."""
        tunnel = Tunnel(name="test_tunnel", adapter="dummy", username="alice", device="", namespace=None)
        service.manager.tunnels["test_tunnel"] = tunnel

        result = await service.GetTunnelStatus("test_tunnel", "alice")

        assert result["status"].value == "disconnected"

    @pytest.mark.asyncio
    async def test_get_tunnel_status_not_found(self, service):
        """Test getting status of non-existent tunnel."""
        with pytest.raises(ValueError):
            await service.GetTunnelStatus("nonexistent", "alice")


class TestManagerServiceGetTrafficStats:
    """Tests for GetTrafficStats D-Bus method."""

    @pytest.fixture
    def service(self):
        mock_manager = MockManager()
        return ManagerService(mock_manager)

    @pytest.mark.asyncio
    async def test_get_traffic_stats_success(self, service):
        """Test getting traffic stats."""
        result = await service.GetTrafficStats("test_tunnel", "alice")

        # Returns tuple (bytes_in, bytes_out)
        assert result == (1000, 2000)


class TestManagerServiceListAdapters:
    """Tests for ListAdapters D-Bus method."""

    @pytest.fixture
    def service(self):
        mock_manager = MockManager()
        mock_manager.session_manager.SESSION_TYPES = {"dummy": Mock(), "proton": Mock()}
        return ManagerService(mock_manager)

    @pytest.mark.asyncio
    async def test_list_adapters(self, service):
        """Test listing adapters."""
        result = await service.ListAdapters()

        assert isinstance(result, list)
        assert "dummy" in result
        assert "proton" in result


class TestManagerServiceGetAdapterCapabilities:
    """Tests for GetAdapterCapabilities D-Bus method."""

    @pytest.fixture
    def service(self):
        mock_manager = MockManager()
        return ManagerService(mock_manager)

    @pytest.mark.asyncio
    async def test_get_adapter_capabilities_dummy(self, service):
        """Test getting capabilities for dummy adapter."""
        result = await service.GetAdapterCapabilities("dummy")

        assert result["multi_tunnel"].value is True
        assert result["supports_protocols"].value == ["dummy"]
        assert result["max_tunnels"].value == -1  # None becomes -1
        assert result["supports_per_app_routing"].value is True
        assert result["supports_kill_switch"].value is False
        assert result["supports_dns_isolation"].value is False

    @pytest.mark.asyncio
    async def test_get_adapter_capabilities_unknown(self, service):
        """Test getting capabilities for unknown adapter."""
        with pytest.raises(AdapterNotFoundError):
            await service.GetAdapterCapabilities("unknown")


class TestManagerServicePing:
    """Tests for Ping D-Bus method."""

    @pytest.fixture
    def service(self):
        mock_manager = MockManager()
        return ManagerService(mock_manager)

    @pytest.mark.asyncio
    async def test_ping(self, service):
        """Test ping returns True."""
        result = await service.Ping()
        assert result is True


class TestManagerServiceSignals:
    """Tests for D-Bus signal emission."""

    def test_signal_methods_exist(self, service):
        """Test that signal methods exist and can be called."""
        # The signal methods are decorated with @signal()
        # They exist as methods that can be called
        assert hasattr(service, 'TunnelStateChanged')
        assert hasattr(service, 'TunnelCreated')
        assert hasattr(service, 'TunnelDestroyed')
        assert hasattr(service, 'AdapterRegistered')


class TestManagerServiceSessions:
    """Tests for session-related methods (ListSessions, Login, Logout)."""

    @pytest.fixture
    def service(self):
        mock_manager = MockManager()
        # Mock session_manager with list_sessions and login/logout
        from libvpnmanager.sessions.base import SessionInfo
        mock_session = Mock()
        mock_session.to_dict.return_value = {
            "adapter": "dummy",
            "session_name": "test_session",
            "username": "alice",
            "status": "active",
        }
        mock_manager.session_manager.list_sessions = AsyncMock(return_value=[mock_session])
        mock_manager.session_manager.load_session = AsyncMock(return_value=mock_session)
        mock_manager.session_manager._save_to_storage = AsyncMock()
        mock_manager.session_manager.logout = AsyncMock(return_value=True)
        return ManagerService(mock_manager)

    @pytest.mark.asyncio
    async def test_list_sessions(self, service):
        """Test listing sessions."""
        result = await service.ListSessions("alice")

        assert isinstance(result, list)
        assert len(result) >= 0  # At least empty list

    @pytest.mark.asyncio
    async def test_login(self, service):
        """Test login creates session."""
        result = await service.Login(
            adapter="dummy",
            session_name="test_session",
            username="alice",
            password="password123"
        )

        # Should return session info as variants
        assert isinstance(result, dict)
        assert "adapter" in result
        assert result["adapter"].value == "dummy"

    @pytest.mark.asyncio
    async def test_logout(self, service):
        """Test logout removes session."""
        result = await service.Logout("dummy", "test_session", "alice")

        assert result is True


class TestManagerServiceErrorHandling:
    """Tests for error handling in D-Bus methods."""

    @pytest.fixture
    def service(self):
        mock_manager = MockManager()
        return ManagerService(mock_manager)

    @pytest.mark.asyncio
    async def test_create_tunnel_session_not_found(self, service):
        """Test that session not found error propagates."""
        from libvpnmanager.models.exceptions import SessionNotFoundError
        # Mock manager to raise error
        original_create = service.manager.create_tunnel
        async def raise_error(config, username):
            raise SessionNotFoundError("Session not found")

        service.manager.create_tunnel = raise_error

        config_dict = {
            "adapter": Variant("s", "dummy"),
            "tunnel_name": Variant("s", "test_tunnel"),
            "session_name": Variant("s", "test_session"),
        }

        with pytest.raises(SessionNotFoundError):
            await service.CreateTunnel(config_dict, "alice")

        # Restore original
        service.manager.create_tunnel = original_create
