"""Pytest fixtures for integration tests."""

import pytest
import asyncio
import sys
from pathlib import Path

# Add mocks to sys.path BEFORE any src imports so that proton.vpn.core.api
# is intercepted by the mock package when the adapter imports it.
MOCKS_PATH = Path(__file__).parent / "mocks"
if str(MOCKS_PATH) not in sys.path:
    sys.path.insert(0, str(MOCKS_PATH))

# Also add to PYTHONPATH so that subprocesses (adapter executables) can import the mock package.
os.environ['PYTHONPATH'] = str(MOCKS_PATH) + ':' + os.environ.get('PYTHONPATH', '')

# Ensure src is in path for imports
SRC_PATH = Path(__file__).parent.parent / "src"
if str(SRC_PATH) not in sys.path:
    sys.path.insert(0, str(SRC_PATH))

from daemon.daemon import VPNDaemon
from libvpnmanager.client import ManagerClient


@pytest.fixture(scope='session', autouse=True)
def require_root():
    """Skip all tests in this module if not running as root."""
    if Path(__file__).parent.name == 'integration':
        import os
        if os.geteuid() != 0:
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

    # Wait for the daemon socket to be created (indicates daemon is listening)
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

    # Request shutdown
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
