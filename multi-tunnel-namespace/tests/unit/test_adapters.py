"""Unit tests for VPN adapters.

Tests cover:
- DummyAdapter lifecycle (connect, disconnect, status, stats)
- DummyAdapter capability reporting
- DummyAdapter multi-tunnel support
- Adapter error handling
- AdapterCapabilities structure
"""

import pytest
import asyncio
from datetime import datetime
from unittest.mock import patch

from libvpnmanager.adapters.dummy import DummyAdapter
from libvpnmanager.adapters.base import AdapterCapabilities, VPNAdapter
from libvpnmanager.models.tunnel import Tunnel
from libvpnmanager.models.config import ConnectionConfig
from libvpnmanager.models.status import TunnelStatus
from libvpnmanager.models.exceptions import TunnelNotFoundError


class TestAdapterCapabilities:
    """Tests for AdapterCapabilities dataclass."""

    def test_capabilities_default_values(self):
        """Test default capability values."""
        caps = AdapterCapabilities()
        assert caps.multi_tunnel is False
        assert caps.supports_protocols == []
        assert caps.max_tunnels is None
        assert caps.supports_per_app_routing is False
        assert caps.supports_kill_switch is False
        assert caps.supports_dns_isolation is False

    def test_capabilities_with_values(self):
        """Test setting capability values."""
        caps = AdapterCapabilities(
            multi_tunnel=True,
            supports_protocols=["wireguard", "openvpn"],
            max_tunnels=10,
            supports_per_app_routing=True,
            supports_kill_switch=True,
            supports_dns_isolation=True,
        )
        assert caps.multi_tunnel is True
        assert len(caps.supports_protocols) == 2
        assert caps.max_tunnels == 10
        assert caps.supports_per_app_routing is True

    def test_capabilities_post_init_initializes_list(self):
        """Test that __post_init__ initializes empty list if None."""
        caps = AdapterCapabilities(supports_protocols=None)
        assert caps.supports_protocols == []


class TestDummyAdapter:
    """Tests for DummyAdapter implementation."""

    @pytest.fixture
    def dummy_adapter(self):
        return DummyAdapter()

    @pytest.fixture
    def dummy_config(self):
        return ConnectionConfig(
            adapter="dummy",
            tunnel_name="test_tunnel",
            session_name="test_session"
        )

    @pytest.mark.asyncio
    async def test_connect_success(self, dummy_adapter, dummy_config):
        """Test successful connection."""
        tunnel = await dummy_adapter.connect(dummy_config)

        assert tunnel.name == "test_tunnel"
        assert tunnel.adapter == "dummy"
        assert tunnel.device.startswith("dummy")
        assert tunnel.namespace == "vpn_test_tunnel"
        assert tunnel.endpoint == "dummy.example.com"
        assert tunnel.connected_at is not None
        assert tunnel.metadata.get("dummy") is True

    @pytest.mark.asyncio
    async def test_connect_with_progress_callback(self, dummy_adapter, dummy_config):
        """Test connection with progress callback."""
        progress_messages = []

        def progress_callback(status):
            progress_messages.append(status)

        tunnel = await dummy_adapter.connect(dummy_config, progress_callback)

        assert "connecting" in progress_messages
        assert "connected" in progress_messages
        assert tunnel.name == "test_tunnel"

    @pytest.mark.asyncio
    async def test_connect_multiple_tunnels(self, dummy_adapter):
        """Test creating multiple tunnels with same adapter."""
        configs = [
            ConnectionConfig(adapter="dummy", tunnel_name=f"tunnel_{i}", session_name="test")
            for i in range(5)
        ]

        tunnels = []
        for config in configs:
            tunnel = await dummy_adapter.connect(config)
            tunnels.append(tunnel)

        # All tunnels should have unique device names
        devices = [t.device for t in tunnels]
        assert len(set(devices)) == 5  # All unique

        # All should be in adapter's list
        all_tunnels = dummy_adapter.list_tunnels()
        assert len(all_tunnels) == 5

    @pytest.mark.asyncio
    async def test_disconnect_success(self, dummy_adapter, dummy_config):
        """Test successful disconnect."""
        tunnel = await dummy_adapter.connect(dummy_config)
        tunnel_name = tunnel.name

        await dummy_adapter.disconnect(tunnel)

        # Tunnel should no longer be in list
        all_tunnels = dummy_adapter.list_tunnels()
        assert all(t.name != tunnel_name for t in all_tunnels)

    @pytest.mark.asyncio
    async def test_disconnect_tunnel_not_found(self, dummy_adapter):
        """Test disconnecting non-existent tunnel raises error."""
        fake_tunnel = Tunnel(
            name="nonexistent",
            adapter="dummy",
            device="dummy1",
        )

        with pytest.raises(TunnelNotFoundError):
            await dummy_adapter.disconnect(fake_tunnel)

    @pytest.mark.asyncio
    async def test_disconnect_with_different_instance(self, dummy_adapter, dummy_config):
        """Test disconnecting with a different Tunnel object (by name lookup)."""
        tunnel1 = await dummy_adapter.connect(dummy_config)

        # Create another Tunnel object with same name (but different instance)
        tunnel2 = Tunnel(
            name=tunnel1.name,
            adapter=tunnel1.adapter,
            device=tunnel1.device,
            namespace=tunnel1.namespace,
        )

        # Should still work because DummyAdapter finds by name
        await dummy_adapter.disconnect(tunnel2)

        all_tunnels = dummy_adapter.list_tunnels()
        assert len(all_tunnels) == 0

    def test_list_tunnels_empty(self, dummy_adapter):
        """Test listing tunnels when none exist."""
        tunnels = dummy_adapter.list_tunnels()
        assert tunnels == []

    def test_list_tunnels_after_connect(self, dummy_adapter, dummy_config):
        """Test listing tunnels after connections."""
        tunnel1 = asyncio.run(dummy_adapter.connect(dummy_config))
        tunnel2 = asyncio.run(
            dummy_adapter.connect(
                ConnectionConfig(adapter="dummy", tunnel_name="tunnel2", session_name="test")
            )
        )

        tunnels = dummy_adapter.list_tunnels()
        assert len(tunnels) == 2
        assert any(t.name == "test_tunnel" for t in tunnels)
        assert any(t.name == "tunnel2" for t in tunnels)

    def test_get_capabilities(self, dummy_adapter):
        """Test DummyAdapter capabilities."""
        caps = dummy_adapter.get_capabilities()

        assert caps.multi_tunnel is True
        assert caps.supports_protocols == ["dummy"]
        assert caps.max_tunnels is None
        # DummyAdapter overrides defaults to enable per-app routing
        assert caps.supports_per_app_routing is True
        assert caps.supports_kill_switch is False
        assert caps.supports_dns_isolation is False

    @pytest.mark.asyncio
    async def test_get_status_connected(self, dummy_adapter, dummy_config):
        """Test get_status for connected tunnel."""
        tunnel = await dummy_adapter.connect(dummy_config)
        status = await dummy_adapter.get_status(tunnel)
        assert status == TunnelStatus.CONNECTED

    @pytest.mark.asyncio
    async def test_get_status_disconnected(self, dummy_adapter, dummy_config):
        """Test get_status for tunnel not in list returns DISCONNECTED."""
        # Create tunnel but don't actually connect it
        tunnel = Tunnel(name="test_tunnel", adapter="dummy", device="")
        status = await dummy_adapter.get_status(tunnel)
        assert status == TunnelStatus.DISCONNECTED

    @pytest.mark.asyncio
    async def test_get_traffic_stats_success(self, dummy_adapter, dummy_config):
        """Test getting traffic stats for connected tunnel."""
        tunnel = await dummy_adapter.connect(dummy_config)
        bytes_in, bytes_out = await dummy_adapter.get_traffic_stats(tunnel)

        assert bytes_in == 12345
        assert bytes_out == 67890

    @pytest.mark.asyncio
    async def test_get_traffic_stats_not_found(self, dummy_adapter):
        """Test getting stats for non-existent tunnel raises error."""
        fake_tunnel = Tunnel(name="nonexistent", adapter="dummy", device="")

        with pytest.raises(TunnelNotFoundError):
            await dummy_adapter.get_traffic_stats(fake_tunnel)

    @pytest.mark.asyncio
    async def test_cleanup(self, dummy_adapter, dummy_config):
        """Test cleanup clears all tunnels."""
        # Create multiple tunnels
        await dummy_adapter.connect(dummy_config)
        await dummy_adapter.connect(
            ConnectionConfig(adapter="dummy", tunnel_name="tunnel2", session_name="test")
        )

        assert len(dummy_adapter.list_tunnels()) == 2

        await dummy_adapter.cleanup()

        tunnels = dummy_adapter.list_tunnels()
        assert tunnels == []

    @pytest.mark.asyncio
    async def test_cleanup_with_errors(self, dummy_adapter):
        """Test that cleanup doesn't raise even if called multiple times."""
        await dummy_adapter.cleanup()
        await dummy_adapter.cleanup()  # Should be safe to call multiple times

    def test_get_adapter_name(self, dummy_adapter):
        """Test get_adapter_name returns correct name."""
        name = dummy_adapter.get_adapter_name()
        assert name == "dummy"

    @pytest.mark.asyncio
    async def test_multiple_tunnels_independence(self, dummy_adapter):
        """Test that multiple tunnels operate independently."""
        configs = [
            ConnectionConfig(adapter="dummy", tunnel_name=f"tunnel_{i}", session_name="test")
            for i in range(3)
        ]

        tunnels = []
        for config in configs:
            tunnel = await dummy_adapter.connect(config)
            tunnels.append(tunnel)

        # Disconnect one
        await dummy_adapter.disconnect(tunnels[0])

        # Others should still be connected
        remaining = dummy_adapter.list_tunnels()
        assert len(remaining) == 2
        assert all(t.name in ["tunnel_1", "tunnel_2"] for t in remaining)

        status0 = await dummy_adapter.get_status(tunnels[0])
        status1 = await dummy_adapter.get_status(tunnels[1])
        assert status0 == TunnelStatus.DISCONNECTED
        assert status1 == TunnelStatus.CONNECTED


class TestVPNAdapterAbstractBase:
    """Tests that VPNAdapter ABC is properly defined."""

    def test_vpn_adapter_is_abstract(self):
        """Test that VPNAdapter cannot be instantiated directly."""
        with pytest.raises(TypeError):
            VPNAdapter()

    def test_vpn_adapter_subclass_must_implement_all_methods(self):
        """Test that subclasses must implement all abstract methods."""

        class IncompleteAdapter(VPNAdapter):
            pass

        with pytest.raises(TypeError):
            IncompleteAdapter()

    def test_vpn_adifier_subclass_works_when_complete(self):
        """Test that complete subclass can be instantiated."""

        class CompleteAdapter(VPNAdapter):
            async def connect(self, config, progress_callback=None):
                return Tunnel(name="test", adapter="complete", device="")

            async def disconnect(self, tunnel):
                pass

            async def get_status(self, tunnel):
                return TunnelStatus.CONNECTED

            def list_tunnels(self):
                return []

            def get_capabilities(self):
                return AdapterCapabilities(multi_tunnel=True)

            async def get_traffic_stats(self, tunnel):
                return (0, 0)

            async def cleanup(self):
                pass

        adapter = CompleteAdapter()
        assert adapter is not None
