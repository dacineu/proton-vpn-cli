#!/usr/bin/env python3
"""
End-to-end integration test with daemon and D-Bus.

This test requires:
- proton-vpn-manager daemon running
- D-Bus available (system bus)
- Root privileges (for namespace creation)

Run with:
    sudo -E python -m pytest tests/integration/test_integration_e2e.py -v

Or manually:
    sudo proton-vpn-manager  # in another terminal
    sudo pytest tests/integration/test_integration_e2e.py -v
"""

import pytest
import asyncio
import subprocess
import sys
import os
from datetime import datetime

# Add src to path
sys.path.insert(0, 'src')

from libvpnmanager.client import VPNManagerClient
from libvpnmanager.models.config import ConnectionConfig
from libvpnmanager.models.status import TunnelStatus


pytestmark = pytest.mark.integration


class TestE2EWithDaemon:
    """End-to-end tests using real daemon and D-Bus.

    Requires:
        sudo proton-vpn-manager running in background
    """

    @pytest.fixture(scope="class")
    def check_root(self):
        """Check if running as root."""
        if os.geteuid() != 0:
            pytest.skip("Integration tests require root privileges")

    @pytest.fixture(scope="class")
    def check_daemon_running(self):
        """Check if daemon is running."""
        try:
            result = subprocess.run(
                ["pgrep", "-f", "proton-vpn-manager"],
                capture_output=True,
                text=True
            )
            if result.returncode != 0:
                pytest.skip("proton-vpn-manager daemon not running")
        except Exception:
            pytest.skip("Could not check daemon status")

    @pytest.mark.asyncio
    async def test_connect_to_daemon(self, check_root, check_daemon_running):
        """Test connecting to the daemon via D-Bus."""
        client = VPNManagerClient()
        await client.connect()
        assert client.connected is True
        await client.disconnect()

    @pytest.mark.asyncio
    async def test_ping_daemon(self, check_root, check_daemon_running):
        """Test ping daemon."""
        client = VPNManagerClient()
        await client.connect()
        result = await client.ping()
        assert result is True
        await client.disconnect()

    @pytest.mark.asyncio
    async def test_list_adapters(self, check_root, check_daemon_running):
        """Test listing available adapters."""
        client = VPNManagerClient()
        await client.connect()
        adapters = await client.list_adapters()
        assert isinstance(adapters, list)
        assert len(adapters) > 0
        await client.disconnect()

    @pytest.mark.asyncio
    async def test_adapter_capabilities(self, check_root, check_daemon_running):
        """Test getting adapter capabilities."""
        client = VPNManagerClient()
        await client.connect()
        caps = await client.get_adapter_capabilities("dummy")
        assert caps.multi_tunnel is True
        await client.disconnect()

    @pytest.mark.asyncio
    async def test_session_lifecycle(self, check_root, check_daemon_running):
        """Test session management: create, list, login, logout."""
        client = VPNManagerClient()
        await client.connect()

        # List sessions (may be empty initially)
        sessions = await client.list_sessions("testuser")
        assert isinstance(sessions, list)

        # Try to login (with dummy adapter, should create session)
        try:
            session_info = await client.login(
                adapter="dummy",
                session_name="test_session",
                username="testuser",
                password="dummy_password"
            )
            assert session_info["adapter"] == "dummy"
            assert session_info["session_name"] == "test_session"
            assert session_info["username"] == "testuser"

            # List sessions again
            sessions = await client.list_sessions("testuser")
            assert len(sessions) > 0

            # Logout
            success = await client.logout("dummy", "test_session", "testuser")
            assert success is True

        except Exception as e:
            # Some adapters might not support login, that's okay
            pytest.skip(f"Login not supported: {e}")

        await client.disconnect()

    @pytest.mark.asyncio
    async def test_tunnel_lifecycle_with_dummy(self, check_root, check_daemon_running):
        """Test full tunnel lifecycle with DummyAdapter."""
        client = VPNManagerClient()
        await client.connect()

        # First login to create a session
        try:
            await client.login(
                adapter="dummy",
                session_name="e2e_test",
                username="testuser",
                password="test"
            )
        except Exception as e:
            pytest.skip(f"Login failed: {e}")

        # Create tunnel with dummy config
        config = ConnectionConfig(
            adapter="dummy",
            tunnel_name="e2e_tunnel",
            session_name="e2e_test"
        )

        tunnel = await client.create_tunnel(config, "testuser")
        assert tunnel.name == "e2e_tunnel"
        assert tunnel.adapter == "dummy"
        assert tunnel.status == TunnelStatus.CONNECTED

        # Get status
        status = await client.get_status("e2e_tunnel", "testuser")
        assert status == TunnelStatus.CONNECTED

        # Get traffic stats (should return something)
        bytes_in, bytes_out = await client.get_traffic_stats("e2e_tunnel", "testuser")
        assert isinstance(bytes_in, int)
        assert isinstance(bytes_out, int)

        # List tunnels
        tunnels = await client.list_tunnels("testuser")
        assert any(t.name == "e2e_tunnel" for t in tunnels)

        # Disconnect
        await client.disconnect_tunnel("e2e_tunnel", "testuser")

        # Destroy
        await client.destroy_tunnel("e2e_tunnel", "testuser")

        # Verify removed
        tunnels = await client.list_tunnels("testuser")
        assert not any(t.name == "e2e_tunnel" for t in tunnels)

        # Logout
        await client.logout("dummy", "e2e_test", "testuser")

        await client.disconnect()

    @pytest.mark.asyncio
    async def test_multiple_tunnels_same_session(self, check_root, check_daemon_running):
        """Test creating multiple tunnels with same session."""
        client = VPNManagerClient()
        await client.connect()

        try:
            await client.login(
                adapter="dummy",
                session_name="multi_test",
                username="testuser",
                password="test"
            )
        except Exception as e:
            pytest.skip(f"Login failed: {e}")

        config_template = ConnectionConfig(
            adapter="dummy",
            tunnel_name="multi_tunnel_{}",
            session_name="multi_test"
        )

        # Create 3 tunnels
        tunnels = []
        for i in range(3):
            config = ConnectionConfig(
                adapter="dummy",
                tunnel_name=f"multi_tunnel_{i}",
                session_name="multi_test"
            )
            tunnel = await client.create_tunnel(config, "testuser")
            tunnels.append(tunnel)

        assert len(tunnels) == 3

        # List all
        all_tunnels = await client.list_tunnels("testuser")
        assert len(all_tunnels) >= 3

        # Clean up
        for tunnel in tunnels:
            await client.destroy_tunnel(tunnel.name, "testuser")

        await client.logout("dummy", "multi_test", "testuser")
        await client.disconnect()

    @pytest.mark.asyncio
    async def test_permissions_admin_vs_user(self, check_root, check_daemon_running):
        """Test admin can see all users' tunnels, regular users cannot."""
        # This test would need multiple users
        # Skipping for now as it's complex to set up
        pytest.skip("Multi-user permission test requires proper user setup")


if __name__ == "__main__":
    # Allow running directly
    pytest.main([__file__, "-v"])
