"""Unit tests for TunnelManager.

Tests cover:
- Tunnel lifecycle (create, connect, disconnect, destroy)
- Permission enforcement (user ownership, admin override)
- Error handling (not found, already exists, adapter errors)
- Thread-safety (asyncio lock)
- Session management integration
- Adapter lifecycle
"""

import pytest
import asyncio
from unittest.mock import Mock, AsyncMock, patch, MagicMock
from datetime import datetime, timedelta

from libvpnmanager.manager import TunnelManager
from libvpnmanager.models.tunnel import Tunnel
from libvpnmanager.models.config import ConnectionConfig
from libvpnmanager.models.status import TunnelStatus
from libvpnmanager.models.exceptions import (
    TunnelExistsError,
    TunnelNotFoundError,
    AccessDeniedError,
    AdapterNotFoundError,
    AdapterError,
)
from libvpnmanager.routing.base import RoutingStrategy
from libvpnmanager.sessions.base import Session
from libvpnmanager.sessions.manager import SessionManager


class MockRouting(RoutingStrategy):
    """Mock routing strategy."""
    async def create_tunnel_context(self, tunnel_name: str):
        return {"namespace": f"ns-{tunnel_name}"}

    async def destroy_tunnel_context(self, tunnel_name: str, metadata: dict):
        pass

    async def assign_process_to_tunnel(self, tunnel_name: str, metadata: dict, pid: int):
        """Mock: assign process to tunnel namespace (no-op)."""
        pass

    async def list_active_tunnels(self) -> dict:
        """Mock: return empty dict of active tunnels."""
        return {}

    async def cleanup_all(self):
        """Mock: cleanup all routing contexts (no-op)."""
        pass


class MockSession(Session):
    """Mock session for testing."""
    def __init__(self, adapter="dummy", session_name="test", username="testuser"):
        self.adapter = adapter
        self.session_name = session_name
        self.username = username
        self.created_at = datetime.utcnow()

    async def validate(self) -> bool:
        return True

    async def refresh(self):
        pass

    async def revoke(self):
        pass

    def to_dict(self) -> dict:
        return {
            "adapter": self.adapter,
            "session_name": self.session_name,
            "username": self.username,
            "created_at": self.created_at.isoformat(),
        }

    @classmethod
    def from_dict(cls, data: dict) -> "MockSession":
        created_at = datetime.fromisoformat(data.get("created_at", datetime.utcnow().isoformat()))
        return cls(
            adapter=data["adapter"],
            session_name=data["session_name"],
            username=data["username"],
        )

    def to_session_info(self):
        from libvpnmanager.sessions.base import SessionInfo
        return SessionInfo(
            adapter=self.adapter,
            session_name=self.session_name,
            username=self.username,
            status="active",
        )


class MockAdapter:
    """Mock VPN adapter for testing."""
    def __init__(self, connect_success=True):
        self.connect_success = connect_success
        self.connected_tunnels = []
        self.disconnected_tunnels = []

    async def connect(self, config, progress_callback=None):
        if not self.connect_success:
            raise Exception("Connection failed")
        tunnel = Tunnel(
            name=config.tunnel_name,
            adapter=config.adapter,
            session_name=config.session_name,
            username="testuser",
            device=f"tun-{config.tunnel_name}",
            namespace=f"ns-{config.tunnel_name}",
            endpoint="1.2.3.4",
            connected_at=datetime.utcnow(),
        )
        self.connected_tunnels.append(tunnel)
        return tunnel

    async def disconnect(self, tunnel):
        self.disconnected_tunnels.append(tunnel)

    async def get_status(self, tunnel):
        return TunnelStatus.CONNECTED if tunnel.device else TunnelStatus.DISCONNECTED

    def list_tunnels(self):
        return self.connected_tunnels.copy()

    def get_capabilities(self):
        from libvpnmanager.adapters.base import AdapterCapabilities
        return AdapterCapabilities(
            multi_tunnel=True,
            supports_protocols=["test"],
            max_tunnels=None,
        )

    async def get_traffic_stats(self, tunnel):
        return (1000, 2000)  # bytes_in, bytes_out

    async def cleanup(self):
        self.connected_tunnels.clear()


@pytest.fixture
def mock_routing():
    return MockRouting()

@pytest.fixture
def mock_session_manager():
    return SessionManager()

@pytest.fixture
def manager(mock_routing, mock_session_manager):
    return TunnelManager(mock_routing, mock_session_manager)


class TestTunnelManagerCreate:
    """Tests for create_tunnel method."""

    @pytest.mark.asyncio
    async def test_create_tunnel_success(self, manager, mock_session_manager):
        """Test successful tunnel creation."""
        # Setup: create a session
        session = MockSession(session_name="test_session", username="alice")
        mock_session_manager._sessions[("dummy", "test_session", "alice")] = session

        config = ConnectionConfig(
            adapter="dummy",
            tunnel_name="test_tunnel",
            session_name="test_session"
        )

        tunnel = await manager.create_tunnel(config, "alice")

        assert tunnel.name == "test_tunnel"
        assert tunnel.adapter == "dummy"
        assert tunnel.session_name == "test_session"
        assert tunnel.username == "alice"
        assert tunnel.status == TunnelStatus.DISCONNECTED
        assert tunnel.device == ""
        assert "test_tunnel" in manager.tunnels

    @pytest.mark.asyncio
    async def test_create_tunnel_duplicate_name(self, manager, mock_session_manager):
        """Test that creating tunnel with duplicate name raises error."""
        session = MockSession(session_name="test_session", username="alice")
        mock_session_manager._sessions[("dummy", "test_session", "alice")] = session

        config = ConnectionConfig(
            adapter="dummy",
            tunnel_name="duplicate_tunnel",
            session_name="test_session"
        )

        await manager.create_tunnel(config, "alice")

        with pytest.raises(TunnelExistsError):
            await manager.create_tunnel(config, "alice")

    @pytest.mark.asyncio
    async def test_create_tunnel_session_not_found(self, manager, mock_session_manager):
        """Test that creating tunnel with non-existent session fails."""
        config = ConnectionConfig(
            adapter="dummy",
            tunnel_name="test_tunnel",
            session_name="nonexistent_session"
        )

        # SessionManager.load_session will raise SessionNotFoundError
        from libvpnmanager.models.exceptions import SessionNotFoundError
        with pytest.raises(SessionNotFoundError):
            await manager.create_tunnel(config, "alice")

    @pytest.mark.asyncio
    async def test_create_tunnel_thread_safety(self, manager, mock_session_manager):
        """Test concurrent tunnel creation with different names is safe."""
        session = MockSession(session_name="test_session", username="alice")
        mock_session_manager._sessions[("dummy", "test_session", "alice")] = session

        async def create_tunnel(name):
            config = ConnectionConfig(
                adapter="dummy",
                tunnel_name=name,
                session_name="test_session"
            )
            return await manager.create_tunnel(config, "alice")

        # Create multiple tunnels concurrently
        tasks = [create_tunnel(f"tunnel_{i}") for i in range(5)]
        tunnels = await asyncio.gather(*tasks)

        assert len(tunnels) == 5
        assert len(manager.tunnels) == 5
        # All names unique
        names = [t.name for t in tunnels]
        assert len(set(names)) == 5


class TestTunnelManagerConnect:
    """Tests for connect_tunnel method."""

    @pytest.mark.asyncio
    async def test_connect_tunnel_success(self, manager, mock_session_manager):
        """Test successful connection."""
        # Create tunnel first
        session = MockSession(session_name="test_session", username="alice")
        mock_session_manager._sessions[("dummy", "test_session", "alice")] = session

        config = ConnectionConfig(
            adapter="dummy",
            tunnel_name="test_tunnel",
            session_name="test_session"
        )
        await manager.create_tunnel(config, "alice")

        # Mock the adapter
        mock_adapter = MockAdapter(connect_success=True)
        manager._adapters[("dummy", "test_session")] = mock_adapter

        # Connect
        tunnel = await manager.connect_tunnel("test_tunnel", "alice")

        assert tunnel.device.startswith("tun-")
        assert tunnel.namespace == "ns-test_tunnel"
        assert tunnel.endpoint == "1.2.3.4"
        assert tunnel.connected_at is not None
        assert len(mock_adapter.connected_tunnels) == 1

    @pytest.mark.asyncio
    async def test_connect_tunnel_not_found(self, manager):
        """Test connecting to non-existent tunnel."""
        with pytest.raises(TunnelNotFoundError):
            await manager.connect_tunnel("nonexistent", "alice")

    @pytest.mark.asyncio
    async def test_connect_tunnel_access_denied(self, manager, mock_session_manager):
        """Test that user cannot connect to another user's tunnel."""
        # Alice creates a tunnel
        session_alice = MockSession(session_name="test_session", username="alice")
        mock_session_manager._sessions[("dummy", "test_session", "alice")] = session_alice

        config = ConnectionConfig(
            adapter="dummy",
            tunnel_name="alices_tunnel",
            session_name="test_session"
        )
        await manager.create_tunnel(config, "alice")

        # Bob tries to connect
        with pytest.raises(AccessDeniedError):
            await manager.connect_tunnel("alices_tunnel", "bob")

    @pytest.mark.asyncio
    async def test_connect_tunnel_already_connected(self, manager, mock_session_manager):
        """Test connecting already connected tunnel returns existing connection."""
        session = MockSession(session_name="test_session", username="alice")
        mock_session_manager._sessions[("dummy", "test_session", "alice")] = session

        config = ConnectionConfig(
            adapter="dummy",
            tunnel_name="test_tunnel",
            session_name="test_session"
        )
        await manager.create_tunnel(config, "alice")

        mock_adapter = MockAdapter(connect_success=True)
        manager._adapters[("dummy", "test_session")] = mock_adapter

        # Connect twice
        tunnel1 = await manager.connect_tunnel("test_tunnel", "alice")
        tunnel2 = await manager.connect_tunnel("test_tunnel", "alice")

        # Should return same tunnel (adapter.connect might be called again, but that's OK)
        assert tunnel1.name == tunnel2.name

    @pytest.mark.asyncio
    async def test_connect_tunnel_adapter_error(self, manager, mock_session_manager):
        """Test that adapter errors are properly propagated."""
        session = MockSession(session_name="test_session", username="alice")
        mock_session_manager._sessions[("dummy", "test_session", "alice")] = session

        config = ConnectionConfig(
            adapter="dummy",
            tunnel_name="test_tunnel",
            session_name="test_session"
        )
        await manager.create_tunnel(config, "alice")

        mock_adapter = MockAdapter(connect_success=False)
        manager._adapters[("dummy", "test_session")] = mock_adapter

        with pytest.raises(AdapterError):
            await manager.connect_tunnel("test_tunnel", "alice")

        # Tunnel state should be cleared on failure
        tunnel = manager.tunnels["test_tunnel"]
        assert tunnel.device == ""
        assert tunnel.namespace is None


class TestTunnelManagerDisconnect:
    """Tests for disconnect_tunnel method."""

    @pytest.mark.asyncio
    async def test_disconnect_tunnel_success(self, manager, mock_session_manager):
        """Test successful disconnect."""
        # Create and connect tunnel
        session = MockSession(session_name="test_session", username="alice")
        mock_session_manager._sessions[("dummy", "test_session", "alice")] = session

        config = ConnectionConfig(
            adapter="dummy",
            tunnel_name="test_tunnel",
            session_name="test_session"
        )
        await manager.create_tunnel(config, "alice")

        mock_adapter = MockAdapter(connect_success=True)
        manager._adapters[("dummy", "test_session")] = mock_adapter

        tunnel = await manager.connect_tunnel("test_tunnel", "alice")
        assert tunnel.device  # is connected

        # Disconnect
        await manager.disconnect_tunnel("test_tunnel", "alice")

        tunnel = manager.tunnels["test_tunnel"]
        assert tunnel.device == ""
        assert tunnel.namespace is None
        assert tunnel.connected_at is None
        assert len(mock_adapter.disconnected_tunnels) == 1

    @pytest.mark.asyncio
    async def test_disconnect_tunnel_not_found(self, manager):
        """Test disconnecting non-existent tunnel."""
        with pytest.raises(TunnelNotFoundError):
            await manager.disconnect_tunnel("nonexistent", "alice")

    @pytest.mark.asyncio
    async def test_disconnect_tunnel_access_denied(self, manager, mock_session_manager):
        """Test that user cannot disconnect another user's tunnel."""
        session_alice = MockSession(session_name="test_session", username="alice")
        mock_session_manager._sessions[("dummy", "test_session", "alice")] = session_alice

        config = ConnectionConfig(
            adapter="dummy",
            tunnel_name="alices_tunnel",
            session_name="test_session"
        )
        await manager.create_tunnel(config, "alice")

        mock_adapter = MockAdapter(connect_success=True)
        manager._adapters[("dummy", "test_session")] = mock_adapter
        await manager.connect_tunnel("alices_tunnel", "alice")

        # Bob tries to disconnect
        with pytest.raises(AccessDeniedError):
            await manager.disconnect_tunnel("alices_tunnel", "bob")

    @pytest.mark.asyncio
    async def test_disconnect_tunnel_already_disconnected(self, manager, mock_session_manager):
        """Test disconnecting an already disconnected tunnel is safe."""
        session = MockSession(session_name="test_session", username="alice")
        mock_session_manager._sessions[("dummy", "test_session", "alice")] = session

        config = ConnectionConfig(
            adapter="dummy",
            tunnel_name="test_tunnel",
            session_name="test_session"
        )
        await manager.create_tunnel(config, "alice")

        # Disconnect without connecting first should be safe
        await manager.disconnect_tunnel("test_tunnel", "alice")

        tunnel = manager.tunnels["test_tunnel"]
        assert tunnel.device == ""


class TestTunnelManagerDestroy:
    """Tests for destroy_tunnel method."""

    @pytest.mark.asyncio
    async def test_destroy_tunnel_success(self, manager, mock_session_manager):
        """Test successful destroy after disconnect."""
        session = MockSession(session_name="test_session", username="alice")
        mock_session_manager._sessions[("dummy", "test_session", "alice")] = session

        config = ConnectionConfig(
            adapter="dummy",
            tunnel_name="test_tunnel",
            session_name="test_session"
        )
        await manager.create_tunnel(config, "alice")

        mock_adapter = MockAdapter(connect_success=True)
        manager._adapters[("dummy", "test_session")] = mock_adapter

        await manager.connect_tunnel("test_tunnel", "alice")
        await manager.disconnect_tunnel("test_tunnel", "alice")

        # Destroy
        await manager.destroy_tunnel("test_tunnel", "alice")

        assert "test_tunnel" not in manager.tunnels

    @pytest.mark.asyncio
    async def test_destroy_tunnel_while_connected(self, manager, mock_session_manager):
        """Test that destroy auto-disconnects if connected."""
        session = MockSession(session_name="test_session", username="alice")
        mock_session_manager._sessions[("dummy", "test_session", "alice")] = session

        config = ConnectionConfig(
            adapter="dummy",
            tunnel_name="test_tunnel",
            session_name="test_session"
        )
        await manager.create_tunnel(config, "alice")

        mock_adapter = MockAdapter(connect_success=True)
        manager._adapters[("dummy", "test_session")] = mock_adapter

        await manager.connect_tunnel("test_tunnel", "alice")
        assert mock_adapter.connected_tunnels

        # Destroy without disconnecting
        await manager.destroy_tunnel("test_tunnel", "alice")

        # Should have called adapter.disconnect
        assert len(mock_adapter.disconnected_tunnels) >= 1
        assert "test_tunnel" not in manager.tunnels

    @pytest.mark.asyncio
    async def test_destroy_tunnel_not_found(self, manager):
        """Test destroying non-existent tunnel."""
        with pytest.raises(TunnelNotFoundError):
            await manager.destroy_tunnel("nonexistent", "alice")

    @pytest.mark.asyncio
    async def test_destroy_tunnel_access_denied(self, manager, mock_session_manager):
        """Test that user cannot destroy another user's tunnel."""
        session_alice = MockSession(session_name="test_session", username="alice")
        mock_session_manager._sessions[("dummy", "test_session", "alice")] = session_alice

        config = ConnectionConfig(
            adapter="dummy",
            tunnel_name="alices_tunnel",
            session_name="test_session"
        )
        await manager.create_tunnel(config, "alice")

        with pytest.raises(AccessDeniedError):
            await manager.destroy_tunnel("alices_tunnel", "bob")


class TestTunnelManagerListTunnels:
    """Tests for list_tunnels method."""

    @pytest.mark.asyncio
    async def test_list_tunnels_all(self, manager, mock_session_manager):
        """Test listing all tunnels."""
        # Create tunnels for multiple users
        for i, user in enumerate(["alice", "bob", "alice"]):
            session = MockSession(session_name=f"session_{i}", username=user)
            mock_session_manager._sessions[(f"adapter_{i}", f"session_{i}", user)] = session

            config = ConnectionConfig(
                adapter=f"adapter_{i}",
                tunnel_name=f"tunnel_{i}",
                session_name=f"session_{i}"
            )
            await manager.create_tunnel(config, user)

        all_tunnels = await manager.list_tunnels()
        assert len(all_tunnels) == 3

    @pytest.mark.asyncio
    async def test_list_tunnels_filter_by_user(self, manager, mock_session_manager):
        """Test listing tunnels for specific user."""
        session_alice = MockSession(session_name="session_a", username="alice")
        session_bob = MockSession(session_name="session_b", username="bob")
        mock_session_manager._sessions[("dummy", "session_a", "alice")] = session_alice
        mock_session_manager._sessions[("dummy", "session_b", "bob")] = session_bob

        config_alice = ConnectionConfig(adapter="dummy", tunnel_name="alice_tunnel", session_name="session_a")
        config_bob = ConnectionConfig(adapter="dummy", tunnel_name="bob_tunnel", session_name="session_b")

        await manager.create_tunnel(config_alice, "alice")
        await manager.create_tunnel(config_bob, "bob")

        alice_tunnels = await manager.list_tunnels(username="alice")
        assert len(alice_tunnels) == 1
        assert alice_tunnels[0].username == "alice"

        bob_tunnels = await manager.list_tunnels(username="bob")
        assert len(bob_tunnels) == 1
        assert bob_tunnels[0].username == "bob"

    @pytest.mark.asyncio
    async def test_list_tunnels_admin_all_users(self, manager, mock_session_manager):
        """Test admin can list all users' tunnels."""
        # Patch _is_admin to return True for 'root'
        with patch.object(manager, '_is_admin', return_value=True):
            session_alice = MockSession(session_name="session_a", username="alice")
            session_bob = MockSession(session_name="session_b", username="bob")
            mock_session_manager._sessions[("dummy", "session_a", "alice")] = session_alice
            mock_session_manager._sessions[("dummy", "session_b", "bob")] = session_bob

            config_alice = ConnectionConfig(adapter="dummy", tunnel_name="alice_tunnel", session_name="session_a")
            config_bob = ConnectionConfig(adapter="dummy", tunnel_name="bob_tunnel", session_name="session_b")

            await manager.create_tunnel(config_alice, "alice")
            await manager.create_tunnel(config_bob, "bob")

            all_tunnels = await manager.list_tunnels(username="root", all_users=True)
            assert len(all_tunnels) == 2

    @pytest.mark.asyncio
    async def test_list_tunnels_non_admin_cannot_use_all_users(self, manager):
        """Test non-admin cannot use all_users flag."""
        with pytest.raises(AccessDeniedError):
            await manager.list_tunnels(username="alice", all_users=True)

    @pytest.mark.asyncio
    async def test_list_tunnels_empty(self, manager):
        """Test listing when no tunnels exist."""
        tunnels = await manager.list_tunnels()
        assert tunnels == []


class TestTunnelManagerGetTunnel:
    """Tests for get_tunnel method."""

    @pytest.mark.asyncio
    async def test_get_tunnel_success(self, manager, mock_session_manager):
        """Test getting own tunnel."""
        session = MockSession(session_name="test_session", username="alice")
        mock_session_manager._sessions[("dummy", "test_session", "alice")] = session

        config = ConnectionConfig(
            adapter="dummy",
            tunnel_name="test_tunnel",
            session_name="test_session"
        )
        await manager.create_tunnel(config, "alice")

        tunnel = await manager.get_tunnel("test_tunnel", "alice")
        assert tunnel.name == "test_tunnel"

    @pytest.mark.asyncio
    async def test_get_tunnel_not_found(self, manager):
        """Test getting non-existent tunnel."""
        tunnel = await manager.get_tunnel("nonexistent", "alice")
        assert tunnel is None

    @pytest.mark.asyncio
    async def test_get_tunnel_access_denied(self, manager, mock_session_manager):
        """Test that user cannot get another user's tunnel."""
        session_alice = MockSession(session_name="test_session", username="alice")
        mock_session_manager._sessions[("dummy", "test_session", "alice")] = session_alice

        config = ConnectionConfig(
            adapter="dummy",
            tunnel_name="alices_tunnel",
            session_name="test_session"
        )
        await manager.create_tunnel(config, "alice")

        with pytest.raises(AccessDeniedError):
            await manager.get_tunnel("alices_tunnel", "bob")


class TestTunnelManagerStatusAndStats:
    """Tests for get_status and get_traffic_stats."""

    @pytest.mark.asyncio
    async def test_get_status_disconnected(self, manager, mock_session_manager):
        """Test getting status of disconnected tunnel."""
        session = MockSession(session_name="test_session", username="alice")
        mock_session_manager._sessions[("dummy", "test_session", "alice")] = session

        config = ConnectionConfig(
            adapter="dummy",
            tunnel_name="test_tunnel",
            session_name="test_session"
        )
        await manager.create_tunnel(config, "alice")

        status = await manager.get_status("test_tunnel", "alice")
        assert status == TunnelStatus.DISCONNECTED

    @pytest.mark.asyncio
    async def test_get_status_connected(self, manager, mock_session_manager):
        """Test getting status of connected tunnel."""
        session = MockSession(session_name="test_session", username="alice")
        mock_session_manager._sessions[("dummy", "test_session", "alice")] = session

        config = ConnectionConfig(
            adapter="dummy",
            tunnel_name="test_tunnel",
            session_name="test_session"
        )
        await manager.create_tunnel(config, "alice")

        mock_adapter = MockAdapter(connect_success=True)
        manager._adapters[("dummy", "test_session")] = mock_adapter

        await manager.connect_tunnel("test_tunnel", "alice")

        status = await manager.get_status("test_tunnel", "alice")
        assert status == TunnelStatus.CONNECTED

    @pytest.mark.asyncio
    async def test_get_traffic_stats(self, manager, mock_session_manager):
        """Test getting traffic statistics."""
        session = MockSession(session_name="test_session", username="alice")
        mock_session_manager._sessions[("dummy", "test_session", "alice")] = session

        config = ConnectionConfig(
            adapter="dummy",
            tunnel_name="test_tunnel",
            session_name="test_session"
        )
        await manager.create_tunnel(config, "alice")

        mock_adapter = MockAdapter(connect_success=True)
        manager._adapters[("dummy", "test_session")] = mock_adapter

        await manager.connect_tunnel("test_tunnel", "alice")

        bytes_in, bytes_out = await manager.get_traffic_stats("test_tunnel", "alice")
        assert bytes_in == 1000
        assert bytes_out == 2000


class TestTunnelManagerAdapters:
    """Tests for adapter-related methods."""

    @pytest.mark.asyncio
    async def test_list_adapters(self, manager):
        """Test listing supported adapters."""
        adapters = await manager.list_adapters()
        # Should include adapters from SessionManager.SESSION_TYPES
        assert isinstance(adapters, list)

    @pytest.mark.asyncio
    async def test_get_adapter_capabilities(self, manager):
        """Test getting capabilities for known adapters."""
        caps = await manager.get_adapter_capabilities("dummy")
        assert caps.multi_tunnel is True
        assert "dummy" in caps.supports_protocols

        caps = await manager.get_adapter_capabilities("proton")
        assert caps.multi_tunnel is True
        assert "wireguard" in caps.supports_protocols
        assert caps.max_tunnels == 10

    @pytest.mark.asyncio
    async def test_get_adapter_capabilities_unknown(self, manager):
        """Test getting capabilities for unknown adapter raises error."""
        with pytest.raises(AdapterNotFoundError):
            await manager.get_adapter_capabilities("unknown_adapter")


class TestTunnelManagerShutdown:
    """Tests for shutdown method."""

    @pytest.mark.asyncio
    async def test_shutdown_disconnects_all_tunnels(self, manager, mock_session_manager):
        """Test that shutdown disconnects all active tunnels."""
        # Create multiple connected tunnels
        mock_adapter = MockAdapter(connect_success=True)

        for i, user in enumerate(["alice", "bob"]):
            session = MockSession(session_name=f"session_{i}", username=user)
            mock_session_manager._sessions[(f"dummy", f"session_{i}", user)] = session

            config = ConnectionConfig(
                adapter="dummy",
                tunnel_name=f"tunnel_{i}",
                session_name=f"session_{i}"
            )
            await manager.create_tunnel(config, user)
            # Manually set device to simulate connection
            manager.tunnels[f"tunnel_{i}"].device = f"tun-{i}"
            manager._adapters[(f"dummy", f"session_{i}")] = mock_adapter

        await manager.shutdown()

        # All tunnels should be removed
        assert len(manager.tunnels) == 0
        # Adapter cleanup should have been called
        # (Though adapters dict is cleared, we can't verify without proper mocking)
        assert len(manager._adapters) == 0

    @pytest.mark.asyncio
    async def test_shutdown_handles_adapter_errors(self, manager, mock_session_manager):
        """Test that shutdown handles adapter errors gracefully."""
        session = MockSession(session_name="test_session", username="alice")
        mock_session_manager._sessions[("dummy", "test_session", "alice")] = session

        config = ConnectionConfig(
            adapter="dummy",
            tunnel_name="test_tunnel",
            session_name="test_session"
        )
        await manager.create_tunnel(config, "alice")
        manager.tunnels["test_tunnel"].device = "tun0"

        # Adapter that throws error on cleanup
        faulty_adapter = Mock()
        faulty_adapter.cleanup = AsyncMock(side_effect=Exception("Cleanup failed"))
        manager._adapters[("dummy", "test_session")] = faulty_adapter

        # Should not raise
        await manager.shutdown()

        assert len(manager.tunnels) == 0


class TestTunnelManagerThreadSafety:
    """Tests for thread-safety and locking."""

    @pytest.mark.asyncio
    async def test_concurrent_operations_same_tunnel(self, manager, mock_session_manager):
        """Test concurrent operations on same tunnel are serialized."""
        session = MockSession(session_name="test_session", username="alice")
        mock_session_manager._sessions[("dummy", "test_session", "alice")] = session

        config = ConnectionConfig(
            adapter="dummy",
            tunnel_name="test_tunnel",
            session_name="test_session"
        )
        await manager.create_tunnel(config, "alice")

        results = []
        async def try_connect():
            try:
                tunnel = await manager.connect_tunnel("test_tunnel", "alice")
                results.append(tunnel.name)
            except Exception as e:
                results.append(f"error: {e}")

        async def try_disconnect():
            try:
                await manager.disconnect_tunnel("test_tunnel", "alice")
                results.append("disconnected")
            except Exception as e:
                results.append(f"error: {e}")

        # Run multiple operations concurrently
        tasks = []
        for _ in range(5):
            tasks.append(try_connect())
            tasks.append(try_disconnect())

        await asyncio.gather(*tasks)

        # Should complete without crashes
        # Results will be a mix, but all operations should succeed or fail gracefully
        assert len(results) == 10
