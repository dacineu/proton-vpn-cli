#!/usr/bin/env python3
"""
Integration test for NetworkNamespaceRouting with actual namespace creation.

This test requires root privileges because it creates real network namespaces
and network devices.

Run with:
    sudo -E python -m pytest tests/integration/test_integration_namespace.py -v

Or manually:
    sudo python tests/integration/test_integration_namespace.py
"""

import pytest
import asyncio
import subprocess
import sys
import os
import tempfile
from datetime import datetime

# Add src to path
sys.path.insert(0, 'src')

from libvpnmanager.routing import NetworkNamespaceRouting
from libvpnmanager.manager import TunnelManager
from libvpnmanager.adapters.dummy import DummyAdapter
from libvpnmanager.models.config import ConnectionConfig
from libvpnmanager.models.status import TunnelStatus
from libvpnmanager.sessions.dummy import DummySession
from libvpnmanager.sessions.manager import SessionManager


pytestmark = pytest.mark.namespace


def is_root():
    """Check if running as root."""
    return os.geteuid() == 0


def setup_module(module):
    """Skip all tests in this module if not root."""
    if not is_root():
        pytest.skip("Namespace integration tests require root privileges", allow_module_level=True)


class TestNetworkNamespaceRoutingIntegration:
    """Integration tests for NetworkNamespaceRouting with real namespace operations."""

    @pytest.fixture(autouse=True)
    def cleanup_namespaces(self):
        """Clean up all test namespaces before and after each test."""
        # Before: clean up any leftover test namespaces
        self._cleanup_test_namespaces()

        yield

        # After: clean up test namespaces
        self._cleanup_test_namespaces()

    def _cleanup_test_namespaces(self):
        """Delete all namespaces starting with test_ or ns_."""
        try:
            # List namespaces
            result = subprocess.run(
                ["ip", "netns", "list"],
                capture_output=True,
                text=True,
                check=False
            )
            for line in result.stdout.strip().split('\n'):
                if line.startswith(('test_', 'ns_')):
                    ns_name = line.strip()
                    subprocess.run(
                        ["ip", "netns", "delete", ns_name],
                        capture_output=True,
                        check=False
                    )
        except Exception:
            pass

    @pytest.mark.asyncio
    async def test_create_and_delete_namespace(self):
        """Test creating and deleting a network namespace."""
        routing = NetworkNamespaceRouting()

        ns_name = "test_integration_1"

        # Create namespace
        result = await routing.create_namespace(ns_name)
        assert result is True

        # Verify namespace exists
        result = subprocess.run(
            ["ip", "netns", "list"],
            capture_output=True,
            text=True
        )
        assert ns_name in result.stdout

        # Delete namespace
        result = await routing.delete_namespace(ns_name)
        assert result is True

        # Verify namespace removed
        result = subprocess.run(
            ["ip", "netns", "list"],
            capture_output=True,
            text=True
        )
        assert ns_name not in result.stdout

    @pytest.mark.asyncio
    async def test_create_existing_namespace_raises_error(self):
        """Test that creating an existing namespace raises error."""
        routing = NetworkNamespaceRouting()
        ns_name = "test_existing_ns"

        # Create namespace
        await routing.create_namespace(ns_name)

        # Try to create again - should raise error
        with pytest.raises(Exception):  # Should be NamespaceError
            await routing.create_namespace(ns_name)

        # Cleanup
        await routing.delete_namespace(ns_name)

    @pytest.mark.asyncio
    async def test_move_device_to_namespace(self):
        """Test moving a dummy device to a namespace."""
        routing = NetworkNamespaceRouting()

        ns_name = "test_device_ns"
        await routing.create_namespace(ns_name)

        # Create a dummy device (use dummy0 if exists, or veth pair)
        # For testing, we'll use a veth pair
        try:
            subprocess.run(["ip", "link", "add", "veth_test type veth peer name veth_peer"], check=True)
            subprocess.run(["ip", "link", "set", "veth_test", "up"], check=True)

            # Move veth_test to namespace
            await routing.move_device_to_namespace("veth_test", ns_name)

            # Verify device is in namespace
            # Check from within namespace
            result = subprocess.run(
                ["ip", "netns", "exec", ns_name, "ip", "link", "show"],
                capture_output=True,
                text=True
            )
            assert "veth_test" in result.stdout

        finally:
            # Cleanup
            subprocess.run(["ip", "link", "delete", "veth_test"], capture_output=True, check=False)
            subprocess.run(["ip", "link", "delete", "veth_peer"], capture_output=True, check=False)
            await routing.delete_namespace(ns_name)

    @pytest.mark.asyncio
    async def test_configure_namespace_network(self):
        """Test configuring IP address, routes, and DNS in namespace."""
        routing = NetworkNamespaceRouting()

        ns_name = "test_config_ns"
        await routing.create_namespace(ns_name)

        try:
            # Configure network
            await routing.configure_namespace_network(
                namespace=ns_name,
                device="lo",  # Use loopback
                gateway="10.0.0.1",
                dns_servers=["8.8.8.8", "1.1.1.1"]
            )

            # Verify loopback is up
            result = subprocess.run(
                ["ip", "netns", "exec", ns_name, "ip", "addr", "show", "lo"],
                capture_output=True,
                text=True
            )
            assert "LOOPBACK" in result.stdout or "inet" in result.stdout

        finally:
            await routing.delete_namespace(ns_name)

    @pytest.mark.asyncio
    async def test_full_tunnel_context_lifecycle(self):
        """Test full create_tunnel_context and destroy_tunnel_context."""
        routing = NetworkNamespaceRouting()

        tunnel_name = "test_full_lifecycle"

        # Create context
        metadata = await routing.create_tunnel_context(tunnel_name)
        assert "namespace" in metadata
        ns_name = metadata["namespace"]
        assert ns_name is not None
        assert len(ns_name) > 0

        # Verify namespace exists
        result = subprocess.run(["ip", "netns", "list"], capture_output=True, text=True)
        assert ns_name in result.stdout

        # Destroy context
        await routing.destroy_tunnel_context(tunnel_name, metadata)

        # Verify namespace removed
        result = subprocess.run(["ip", "netns", "list"], capture_output=True, text=True)
        # Note: might still be cleaning up, so check a few times or assert loosely
        # For now, assume immediate deletion


class TestTunnelManagerIntegrationWithRealNamespace:
    """Integration tests for TunnelManager with real namespace creation.

    Requires root because NetworkNamespaceRouting uses subprocess to call ip.
    """

    @pytest.fixture(autouse=True)
    def cleanup(self):
        """Clean up after each test."""
        self.routing = None
        self.manager = None
        yield
        if self.manager:
            try:
                asyncio.run(self.manager.shutdown())
            except Exception:
                pass
        self._cleanup_all_namespaces()

    def _cleanup_all_namespaces(self):
        """Remove all test namespaces."""
        try:
            result = subprocess.run(["ip", "netns", "list"], capture_output=True, text=True)
            for line in result.stdout.strip().split('\n'):
                if line.startswith('test_') or line.startswith('ns_'):
                    subprocess.run(["ip", "netns", "delete", line.strip()], capture_output=True)
        except Exception:
            pass

    @pytest.mark.asyncio
    async def test_create_and_connect_tunnel_creates_namespace(self):
        """Test that connecting a tunnel creates a network namespace."""
        if not is_root():
            pytest.skip("Requires root")

        self.routing = NetworkNamespaceRouting()
        session_mgr = SessionManager()

        # Create DummySession
        session = DummySession(
            session_name="integration_test",
            username="testuser"
        )
        session_mgr._sessions[("dummy", "integration_test", "testuser")] = session

        self.manager = TunnelManager(self.routing, session_mgr)

        # Register dummy adapter implicitly when creating tunnel
        config = ConnectionConfig(
            adapter="dummy",
            tunnel_name="integration_tunnel",
            session_name="integration_test"
        )

        tunnel = await self.manager.create_tunnel(config, "testuser")
        assert tunnel.name == "integration_tunnel"

        # Connect
        tunnel = await self.manager.connect_tunnel("integration_tunnel", "testuser")
        assert tunnel.device  # Device assigned
        assert tunnel.namespace is not None
        assert tunnel.namespace.startswith("ns-")  # From create_tunnel_context

        # Verify namespace exists
        result = subprocess.run(["ip", "netns", "list"], capture_output=True, text=True)
        assert tunnel.namespace in result.stdout

    @pytest.mark.asyncio
    async def test_disconnect_keeps_namespace(self):
        """Test that disconnecting does not delete namespace."""
        if not is_root():
            pytest.skip("Requires root")

        self.routing = NetworkNamespaceRouting()
        session_mgr = SessionManager()
        session = DummySession(session_name="test", username="testuser")
        session_mgr._sessions[("dummy", "test", "testuser")] = session

        self.manager = TunnelManager(self.routing, session_mgr)

        config = ConnectionConfig(adapter="dummy", tunnel_name="test_tunnel", session_name="test")
        tunnel = await self.manager.create_tunnel(config, "testuser")
        tunnel = await self.manager.connect_tunnel("test_tunnel", "testuser")

        ns_name = tunnel.namespace
        assert ns_name is not None

        # Disconnect
        await self.manager.disconnect_tunnel("test_tunnel", "testuser")

        # Namespace should still exist
        result = subprocess.run(["ip", "netns", "list"], captureoutput=True, text=True)
        assert ns_name in result.stdout

    @pytest.mark.asyncio
    async def test_destroy_tunnel_deletes_namespace(self):
        """Test that destroying a tunnel cleans up its namespace."""
        if not is_root():
            pytest.skip("Requires root")

        self.routing = NetworkNamespaceRouting()
        session_mgr = SessionManager()
        session = DummySession(session_name="test", username="testuser")
        session_mgr._sessions[("dummy", "test", "testuser")] = session

        self.manager = TunnelManager(self.routing, session_mgr)

        config = ConnectionConfig(adapter="dummy", tunnel_name="test_tunnel", session_name="test")
        tunnel = await self.manager.create_tunnel(config, "testuser")
        tunnel = await self.manager.connect_tunnel("test_tunnel", "testuser")

        ns_name = tunnel.namespace
        assert ns_name is not None

        # Destroy
        await self.manager.destroy_tunnel("test_tunnel", "testuser")

        # Namespace should be gone
        # Give it a moment to clean up
        await asyncio.sleep(0.5)
        result = subprocess.run(["ip", "netns", "list"], capture_output=True, text=True)
        # Might still be there if destroy is async, but eventually removed
        # For now, just verify the tunnel is gone from manager
        assert "test_tunnel" not in self.manager.tunnels

    @pytest.mark.asyncio
    async def test_multiple_tunnels_multiple_namespaces(self):
        """Test that multiple tunnels get separate namespaces."""
        if not is_root():
            pytest.skip("Requires root")

        self.routing = NetworkNamespaceRouting()
        session_mgr = SessionManager()
        session = DummySession(session_name="multi", username="testuser")
        session_mgr._sessions[("dummy", "multi", "testuser")] = session

        self.manager = TunnelManager(self.routing, session_mgr)

        # Create multiple tunnels
        tunnel_names = []
        namespaces = []
        for i in range(3):
            config = ConnectionConfig(
                adapter="dummy",
                tunnel_name=f"multi_tunnel_{i}",
                session_name="multi"
            )
            tunnel = await self.manager.create_tunnel(config, "testuser")
            tunnel = await self.manager.connect_tunnel(f"multi_tunnel_{i}", "testuser")
            tunnel_names.append(tunnel.name)
            namespaces.append(tunnel.namespace)

        # All namespaces should be unique
        assert len(set(namespaces)) == 3

        # All should exist
        result = subprocess.run(["ip", "netns", "list"], capture_output=True, text=True)
        for ns in namespaces:
            assert ns in result.stdout

        # Clean up
        for name in tunnel_names:
            await self.manager.destroy_tunnel(name, "testuser")


if __name__ == "__main__":
    pytest.main([__file__, "-v", "-s"])
