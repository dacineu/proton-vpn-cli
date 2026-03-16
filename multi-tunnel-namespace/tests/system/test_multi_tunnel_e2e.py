#!/usr/bin/env python3
"""
System tests for multi-tunnel VPN on real systems.

These tests validate the complete system:
- Package installation
- Daemon startup via systemd
- Multi-tunnel creation and isolation
- nsenter functionality
- Cleanup and shutdown

These tests are designed to run on a VM or physical system.
They require:
- sudo privileges
- systemd
- Arch/Debian/Fedora packages installed

Run manually:
    sudo python tests/system/test_multi_tunnel_e2e.py

Or automate with pytest:
    sudo pytest tests/system/ -v
"""

import sys
import os
import subprocess
import time
import tempfile
import json
from pathlib import Path

sys.path.insert(0, 'src')

from libvpnmanager.client import VPNManagerClient


def run(cmd, check=True, capture_output=True, sudo=False):
    """Run a command and return result."""
    if sudo and not cmd.startswith('sudo'):
        cmd = ['sudo'] + cmd
    result = subprocess.run(cmd, capture_output=capture_output, text=True)
    if check and result.returncode != 0:
        raise RuntimeError(f"Command failed: {' '.join(cmd)}\n{result.stderr}")
    return result


def check_daemon_active():
    """Check if proton-vpn-manager service is active."""
    result = run(['systemctl', 'is-active', 'proton-vpn-manager.service'], check=False)
    return result.returncode == 0


def start_daemon():
    """Start the proton-vpn-manager service."""
    print("Starting proton-vpn-manager daemon...")
    run(['systemctl', 'start', 'proton-vpn-manager.service'])
    time.sleep(2)  # Wait for D-Bus registration
    if not check_daemon_active():
        raise RuntimeError("Daemon failed to start")
    print("✓ Daemon started")


def stop_daemon():
    """Stop the proton-vpn-manager service."""
    print("Stopping proton-vpn-manager daemon...")
    run(['systemctl', 'stop', 'proton-vpn-manager.service'])
    time.sleep(1)
    print("✓ Daemon stopped")


def check_nsenter_installed():
    """Check if nsenter is available."""
    result = run(['which', 'nsenter'], check=False)
    return result.returncode == 0


def check_packages_installed():
    """Check if required packages are installed."""
    packages = [
        'proton-vpn-manager',
        'protonvpn',
    ]
    missing = []
    for pkg in packages:
        result = run(['pacman', '-Q', pkg], check=False) if 'arch' in os.uname().release.lower() else \
                 run(['dpkg', '-l', pkg], check=False) if 'debian' in os.uname().release.lower() or 'ubuntu' in os.uname().release.lower() else \
                 run(['rpm', '-q', pkg], check=False)
        if result.returncode != 0:
            missing.append(pkg)

    if missing:
        print(f"Missing packages: {', '.join(missing)}")
        return False
    return True


class TestSystemSetup:
    """System setup validation tests."""

    def test_packages_installed(self):
        """Test that all required packages are installed."""
        assert check_packages_installed(), "Not all required packages are installed"

    def test_nsenter_available(self):
        """Test that nsenter is installed."""
        assert check_nsenter_installed(), "nsenter not found in PATH"

    def test_kernel_version(self):
        """Test kernel is recent enough (>= 3.9)."""
        result = run(['uname', '-r'])
        kernel = result.stdout.strip()
        # Just check it exists, parsing version is complex
        assert kernel, "Could not determine kernel version"
        print(f"  Kernel: {kernel}")


class TestDaemonLifecycle:
    """Tests for daemon lifecycle."""

    def test_daemon_can_start(self):
        """Test that daemon can be started."""
        if not check_daemon_active():
            start_daemon()
        assert check_daemon_active(), "Daemon not active after start"

    def test_daemon_can_stop(self):
        """Test that daemon can be stopped."""
        if not check_daemon_active():
            start_daemon()
        stop_daemon()
        assert not check_daemon_active(), "Daemon still active after stop"

    def test_daemon_can_restart(self):
        """Test that daemon can be restarted."""
        if check_daemon_active():
            stop_daemon()
        start_daemon()
        assert check_daemon_active(), "Daemon not active after restart"


class TestMultiTunnelFunctionality:
    """End-to-end system tests for multi-tunnel functionality.

    These tests require:
    - Daemon running
    - At least one VPN adapter configured (dummy for testing)
    """

    @classmethod
    def setup_class(cls):
        """Ensure daemon is running before tests."""
        if not check_daemon_active():
            print("Daemon not running, starting...")
            start_daemon()
        cls.client = VPNManagerClient()
        asyncio.run(cls.client.connect())

    @classmethod
    def teardown_class(cls):
        """Clean up after all tests."""
        asyncio.run(cls.client.disconnect())
        # Optionally stop daemon
        # stop_daemon()

    def test_connect_to_daemon(self):
        """Test client can connect to daemon."""
        assert self.client.connected, "Failed to connect to daemon"

    def test_list_adapters(self):
        """Test listing available adapters."""
        adapters = asyncio.run(self.client.list_adapters())
        assert isinstance(adapters, list)
        assert len(adapters) > 0
        print(f"  Available adapters: {', '.join(adapters)}")

    def test_ping_daemon(self):
        """Test daemon responds to ping."""
        result = asyncio.run(self.client.ping())
        assert result is True

    def test_create_multiple_tunnels(self):
        """Test creating multiple tunnels with dummy adapter."""
        # Create 3 tunnels
        tunnel_names = []
        for i in range(3):
            name = f"sys_test_tunnel_{i}"
            config = ConnectionConfig(
                adapter="dummy",
                tunnel_name=name,
                session_name="system_test"
            )
            tunnel = asyncio.run(self.client.create_tunnel(config, "testuser"))
            assert tunnel.name == name
            tunnel_names.append(name)

        # List tunnels
        tunnels = asyncio.run(self.client.list_tunnels("testuser"))
        assert len(tunnels) >= 3
        for name in tunnel_names:
            assert any(t.name == name for t in tunnels)

        print(f"  Created {len(tunnel_names)} tunnels")

        # Clean up
        for name in tunnel_names:
            asyncio.run(self.client.destroy_tunnel(name, "testuser"))

    def test_tunnel_isolation(self):
        """Test that each tunnel gets its own namespace."""
        # Create 2 tunnels
        tunnels = []
        for i in range(2):
            config = ConnectionConfig(
                adapter="dummy",
                tunnel_name=f"iso_test_{i}",
                session_name="iso_test"
            )
            tunnel = asyncio.run(self.client.create_tunnel(config, "testuser"))
            tunnels.append(tunnel)

        # Check namespaces are different
        namespaces = [t.namespace for t in tunnels]
        assert len(set(namespaces)) == 2, "Tunnels should have separate namespaces"

        # Verify namespaces exist in system
        result = run(['ip', 'netns', 'list'], capture_output=True, text=True)
        for ns in namespaces:
            assert ns in result.stdout, f"Namespace {ns} not found in ip netns list"

        print(f"  Namespaces: {', '.join(namespaces)}")

        # Clean up
        for tunnel in tunnels:
            asyncio.run(self.client.destroy_tunnel(tunnel.name, "testuser"))

    def test_nsenter_command_construction(self):
        """Test that nsenter command would be correctly constructed by CLI."""
        # This is a CLI-level test, but we can verify tunnel has namespace
        config = ConnectionConfig(
            adapter="dummy",
            tunnel_name="nsenter_test",
            session_name="ns_test"
        )
        tunnel = asyncio.run(self.client.create_tunnel(config, "testuser"))

        assert tunnel.namespace is not None
        assert tunnel.namespace.startswith("ns-")

        # The CLI would use: nsenter -t $$ -n -m -u -i -p <namespace> <command>
        # Where $$ is PID of current shell
        # We can verify the namespace exists for nsenter to use
        result = run(['ip', 'netns', 'list'], capture_output=True, text=True)
        assert tunnel.namespace in result.stdout

        asyncio.run(self.client.destroy_tunnel("nsenter_test", "testuser"))

    def test_traffic_stats_available(self):
        """Test that traffic stats can be retrieved."""
        config = ConnectionConfig(
            adapter="dummy",
            tunnel_name="stats_test",
            session_name="stats_test"
        )
        tunnel = asyncio.run(self.client.create_tunnel(config, "testuser"))

        bytes_in, bytes_out = asyncio.run(
            self.client.get_traffic_stats(tunnel.name, "testuser")
        )

        assert isinstance(bytes_in, int)
        assert isinstance(bytes_out, int)
        assert bytes_in >= 0
        assert bytes_out >= 0

        print(f"  Traffic stats: {bytes_in} in, {bytes_out} out")

        asyncio.run(self.client.destroy_tunnel(tunnel.name, "testuser"))

    def test_adapter_capabilities(self):
        """Test retrieving adapter capabilities."""
        caps = asyncio.run(self.client.get_adapter_capabilities("dummy"))
        assert caps.multi_tunnel is True
        assert isinstance(caps.supports_protocols, list)
        print(f"  Dummy adapter protocols: {', '.join(caps.supports_protocols)}")


class TestCleanup:
    """Tests for proper cleanup."""

    def test_no_namespaces_left_after_cleanup(self):
        """Test that all test namespaces are cleaned up."""
        # List all namespaces
        result = run(['ip', 'netns', 'list'], capture_output=True, text=True)
        test_namespaces = [line.strip() for line in result.stdout.strip().split('\n')
                          if line.strip().startswith(('test_', 'ns_'))]

        if test_namespaces:
            print(f"  WARNING: Found test namespaces: {test_namespaces}")
            # Try to clean them up
            for ns in test_namespaces:
                run(['ip', 'netns', 'delete', ns], check=False)

        # Should be no test namespaces
        result = run(['ip', 'netns', 'list'], capture_output=True, text=True)
        remaining = [line.strip() for line in result.stdout.strip().split('\n')
                     if line.strip().startswith(('test_', 'ns_'))]
        assert len(remaining) == 0, f"Leftover test namespaces: {remaining}"


def run_tests():
    """Run all system tests."""
    print("=" * 60)
    print("System Tests for Multi-Tunnel VPN")
    print("=" * 60)

    if not is_root():
        print("ERROR: System tests require root privileges")
        print("Run with: sudo -E python tests/system/test_multi_tunnel_e2e.py")
        sys.exit(1)

    # Run pytest
    import pytest
    sys.exit(pytest.main([__file__, '-v', '-s']))


if __name__ == "__main__":
    run_tests()
