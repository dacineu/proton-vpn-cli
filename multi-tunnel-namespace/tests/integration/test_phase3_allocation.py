"""Integration tests for Phase 3: Full AllocateTunnel resource allocation.

This test verifies that the AllocateTunnel handler correctly:
- Creates a network namespace
- Moves the device into the namespace
- Configures the network (IP, route, DNS)
- Returns complete metadata
And that ReleaseTunnel cleans up the namespace.
"""

import pytest
import asyncio
import os
import subprocess
import sys
from pathlib import Path

# Ensure src is in sys.path
SRC_PATH = Path(__file__).parent.parent / "src"
if str(SRC_PATH) not in sys.path:
    sys.path.insert(0, str(SRC_PATH))

# Add mocks to sys.path for proton.vpn.core.api mock (though using dummy adapter)
MOCKS_PATH = Path(__file__).parent / "mocks"
if str(MOCKS_PATH) not in sys.path:
    sys.path.insert(0, str(MOCKS_PATH))

from daemon.daemon import VPNDaemon
from libvpnmanager.client import ManagerClient, AdapterClient
from libvpnmanager.models.config import ConnectionConfig
from libvpnmanager.models.tunnel import Tunnel

pytestmark = pytest.mark.integration


@pytest.fixture(scope='session', autouse=True)
def require_root():
    """Skip all tests in this module if not running as root."""
    if Path(__file__).parent.name == 'integration':
        import os as os_mod
        if os_mod.geteuid() != 0:
            pytest.skip("Integration tests require root privileges")


@pytest.fixture
async def daemon(tmp_path):
    """Start a VPNDaemon instance with temporary paths."""
    socket_path = tmp_path / "daemon.sock"
    adapter_dir = tmp_path / "adapters"
    internal_socket = tmp_path / "internal.sock"

    daemon = VPNDaemon(
        ipc_socket_path=str(socket_path),
        adapter_dir=str(adapter_dir),
        internal_socket=str(internal_socket)
    )
    task = asyncio.create_task(daemon.start())

    # Wait for daemon socket
    timeout = 5.0
    start_time = asyncio.get_event_loop().time()
    while not socket_path.exists():
        await asyncio.sleep(0.1)
        if asyncio.get_event_loop().time() - start_time > timeout:
            task.cancel()
            try:
                await task
            except asyncio.CancelledError:
                pass
            raise RuntimeError("Daemon failed to create socket within timeout")

    yield daemon

    # Stop daemon
    daemon.stop()
    try:
        await asyncio.wait_for(task, timeout=5.0)
    except asyncio.TimeoutError:
        task.cancel()
        try:
            await task
        except asyncio.CancelledError:
            pass
        raise


@pytest.fixture
async def manager_client(daemon):
    """Provide a connected ManagerClient instance."""
    client = ManagerClient(socket_path=daemon.ipc_socket_path)
    await client.connect()
    yield client
    await client.disconnect()


@pytest.fixture
def dummy_credentials():
    return {'username': 'testuser', 'password': 'testpass'}


@pytest.fixture
def session_token():
    # We'll obtain real token via verify_2fa in the test
    return 'dummy-token'


@pytest.fixture
def veth_setup():
    """Create a veth pair for device movement and clean up peer after test."""
    veth_in = "veth_test_in"
    veth_peer = "veth_test_peer"
    # Create veth pair
    try:
        subprocess.run(
            ["ip", "link", "add", veth_in, "type", "veth", "peer", "name", veth_peer],
            check=True, capture_output=True
        )
        subprocess.run(["ip", "link", "set", veth_in, "up"], check=True, capture_output=True)
        # veth_peer remains down; that's fine.
        yield veth_in, veth_peer
    finally:
        # Cleanup peer (veth_in may have been moved to namespace and will be deleted with namespace)
        try:
            subprocess.run(["ip", "link", "delete", veth_peer], check=False, capture_output=True)
        except Exception:
            pass


@pytest.mark.asyncio
async def test_full_allocation(manager_client, dummy_credentials, veth_setup):
    """Test full resource allocation: device movement, network configuration, DNS."""
    veth_in, veth_peer = veth_setup

    # Set environment variable so dummy adapter uses this device
    os.environ['TEST_DUMMY_DEVICE'] = veth_in

    # Get session token via 2FA (dummy)
    totp_result = await manager_client.verify_2fa('123456')
    session_token_val = totp_result['session_token']
    assert session_token_val is not None

    try:
        # Start dummy adapter
        endpoint = await manager_client.start_adapter('dummy', dummy_credentials, session_token=session_token_val)
        assert endpoint.startswith('unix://')
        socket_path = endpoint.replace('unix://', '')
        assert Path(socket_path).exists()

        # Connect to adapter and create tunnel
        async with AdapterClient(endpoint, session_token=session_token_val) as adapter:
            config = ConnectionConfig(adapter='dummy', tunnel_name='test-tunnel')
            tunnel = await adapter.create_tunnel('test-tunnel', config)

            # Verify response contains required fields
            assert isinstance(tunnel, Tunnel)
            assert tunnel.namespace is not None
            assert tunnel.namespace.startswith('vpn_')
            assert tunnel.device == veth_in
            assert tunnel.gateway == "10.8.0.1"
            assert tunnel.dns_servers == ["1.1.1.1", "1.0.0.1"]
            assert tunnel.vpn_ip == "10.8.0.2"

            # Verify namespace exists in system
            result = subprocess.run(['ip', 'netns', 'list'], capture_output=True, text=True)
            assert tunnel.namespace in result.stdout.split()

            # Verify device is in namespace and is UP
            result = subprocess.run(
                ['ip', 'netns', 'exec', tunnel.namespace, 'ip', 'link', 'show', tunnel.device],
                capture_output=True, text=True
            )
            assert result.returncode == 0
            assert tunnel.device in result.stdout
            # Check device state (should be UP)
            # ip link show output contains "state UP" or just "UP"
            assert 'state UP' in result.stdout or 'UP' in result.stdout

            # Verify default route
            result = subprocess.run(
                ['ip', 'netns', 'exec', tunnel.namespace, 'ip', 'route'],
                capture_output=True, text=True
            )
            assert result.returncode == 0
            expected_route = f"default via {tunnel.gateway} dev {tunnel.device}"
            assert expected_route in result.stdout

            # Verify DNS configuration
            result = subprocess.run(
                ['ip', 'netns', 'exec', tunnel.namespace, 'cat', '/etc/resolv.conf'],
                capture_output=True, text=True
            )
            assert result.returncode == 0
            for dns in tunnel.dns_servers:
                assert dns in result.stdout

            # Destroy tunnel to trigger ReleaseTunnel and namespace deletion
            destroyed = await adapter.destroy_tunnel(tunnel.name)
            assert destroyed

        # Verify namespace is deleted after release
        # Note: deletion might be immediate; poll briefly
        for _ in range(5):
            result = subprocess.run(['ip', 'netns', 'list'], capture_output=True, text=True)
            if tunnel.namespace not in result.stdout.split():
                break
            await asyncio.sleep(0.1)
        else:
            # Still present after timeout, fail
            assert tunnel.namespace not in result.stdout.split(), f"Namespace {tunnel.namespace} still exists after release"

    finally:
        # Cleanup environment
        if 'TEST_DUMMY_DEVICE' in os.environ:
            del os.environ['TEST_DUMMY_DEVICE']
        # Ensure veth_peer is deleted (if test failed before namespace deletion)
        try:
            subprocess.run(['ip', 'link', 'delete', veth_peer], check=False, capture_output=True)
        except Exception:
            pass
