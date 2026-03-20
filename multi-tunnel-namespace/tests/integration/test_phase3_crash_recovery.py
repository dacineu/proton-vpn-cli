"""Integration test for Phase 3: Adapter crash cleanup (DAEM-05)."""

import pytest
import asyncio
import os
import signal
import subprocess
import sys
from pathlib import Path
from unittest.mock import patch

SRC_PATH = Path(__file__).parent.parent / "src"
if str(SRC_PATH) not in sys.path:
    sys.path.insert(0, str(SRC_PATH))

MOCKS_PATH = Path(__file__).parent / "mocks"
if str(MOCKS_PATH) not in sys.path:
    sys.path.insert(0, str(MOCKS_PATH))

from daemon.daemon import VPNDaemon
from libvpnmanager.client import ManagerClient, AdapterClient
from libvpnmanager.models.config import ConnectionConfig

pytestmark = pytest.mark.integration


@pytest.fixture(scope='session', autouse=True)
def require_root():
    if Path(__file__).parent.name == 'integration':
        import os as os_mod
        if os_mod.geteuid() != 0:
            pytest.skip("Integration tests require root privileges")


@pytest.fixture
async def daemon(tmp_path):
    socket_path = tmp_path / "daemon.sock"
    adapter_dir = tmp_path / "adapters"
    internal_socket = tmp_path / "internal.sock"
    daemon = VPNDaemon(
        ipc_socket_path=str(socket_path),
        adapter_dir=str(adapter_dir),
        internal_socket=str(internal_socket)
    )
    task = asyncio.create_task(daemon.start())
    timeout = 5.0
    start = asyncio.get_event_loop().time()
    while not socket_path.exists():
        await asyncio.sleep(0.1)
        if asyncio.get_event_loop().time() - start > timeout:
            task.cancel()
            try:
                await task
            except asyncio.CancelledError:
                pass
            raise RuntimeError("Daemon failed to start")
    yield daemon
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
    client = ManagerClient(socket_path=daemon.ipc_socket_path)
    await client.connect()
    yield client
    await client.disconnect()


@pytest.fixture
def dummy_credentials():
    return {'username': 'testuser', 'password': 'testpass'}


@pytest.fixture
def veth_setup():
    veth_in = "veth_crash_in"
    veth_peer = "veth_crash_peer"
    try:
        subprocess.run(
            ["ip", "link", "add", veth_in, "type", "veth", "peer", "name", veth_peer],
            check=True, capture_output=True
        )
        subprocess.run(["ip", "link", "set", veth_in, "up"], check=True, capture_output=True)
        yield veth_in, veth_peer
    finally:
        try:
            subprocess.run(["ip", "link", "delete", veth_peer], check=False, capture_output=True)
        except Exception:
            pass


@pytest.mark.asyncio
async def test_adapter_crash_cleanup(daemon, manager_client, dummy_credentials, veth_setup):
    """Test that when an adapter crashes, its tunnel namespaces are cleaned up."""
    veth_in, veth_peer = veth_setup
    os.environ['TEST_DUMMY_DEVICE'] = veth_in

    # Start adapter
    totp_result = await manager_client.verify_2fa('123456')
    session_token = totp_result['session_token']
    endpoint = await manager_client.start_adapter('dummy', dummy_credentials, session_token=session_token)

    async with AdapterClient(endpoint, session_token=session_token) as adapter:
        config = ConnectionConfig(adapter='dummy', tunnel_name='crash-test')
        tunnel = await adapter.create_tunnel('crash-test', config)
        namespace = tunnel.namespace
        assert namespace is not None

        # Verify namespace exists
        result = subprocess.run(['ip', 'netns', 'list'], capture_output=True, text=True)
        assert namespace in result.stdout

        # Get the adapter instance from the daemon registry to obtain its PID
        # The adapter registry stores by (type, session_name)
        # The session_name for the adapter is stored in the adapter's global? We can get it from the registry.
        # The daemon fixture provides the daemon instance.
        # The adapter instance should be in daemon.adapter_registry.adapters.
        # We can find the key for our adapter. The username is dummy_credentials['username'].
        key = ('dummy', dummy_credentials['username'])
        await asyncio.sleep(0.1)  # allow registration to settle
        adapter_instance = daemon.adapter_registry.adapters.get(key)
        assert adapter_instance is not None, "Adapter should be registered"
        pid = adapter_instance.process.pid
        assert pid is not None and pid > 0

    # At this point, the adapter client has disconnected, but the adapter process is still running (since we only closed CLI connection, not stopped adapter). Actually, the adapter process continues running until StopAdapter or idle timeout. We want to simulate crash, so we kill it.
    # Send SIGKILL to the adapter process
    os.kill(pid, signal.SIGKILL)

    # Wait for the daemon to detect the process exit and perform cleanup
    # Poll for namespace deletion
    namespace_deleted = False
    for _ in range(20):
        result = subprocess.run(['ip', 'netns', 'list'], capture_output=True, text=True)
        if namespace not in result.stdout:
            namespace_deleted = True
            break
        await asyncio.sleep(0.2)
    assert namespace_deleted, f"Namespace {namespace} should have been deleted after adapter crash"

    # Verify adapter removed from registry
    assert key not in daemon.adapter_registry.adapters, "Adapter should be unregistered after crash"
