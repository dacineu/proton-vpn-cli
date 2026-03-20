"""Unit tests for adapter crash cleanup (DAEM-05)."""

import pytest
import asyncio
from unittest.mock import MagicMock, AsyncMock
from daemon.adapter_registry import AdapterRegistry, AdapterInstance


@pytest.fixture
def registry():
    """Create a fresh AdapterRegistry."""
    return AdapterRegistry(adapter_dir="/tmp/test_adapters")


@pytest.mark.asyncio
async def test_unregister_by_pid_triggers_crash_cleanup(registry):
    """Test that _unregister_by_pid calls release_adapter_tunnels on crash."""
    # Mock resource allocator
    mock_allocator = MagicMock()
    mock_allocator.release_adapter_tunnels = AsyncMock()
    registry.set_resource_allocator(mock_allocator)

    # Create a fake adapter instance with tunnels
    fake_process = MagicMock(spec=asyncio.subprocess.Process)
    fake_process.returncode = None
    adapter = AdapterInstance(
        adapter_type='dummy',
        session_name='testsession',
        process=fake_process,
        control_socket='/tmp/test.sock',
        session_id='session123',
        username='testuser',
        tunnels={'tunnel1', 'tunnel2'}
    )

    # Register by pid
    pid = 12345
    async with registry._lock:
        registry._by_pid[pid] = adapter
        registry.adapters[('dummy', 'testsession')] = adapter

    # Call _unregister_by_pid
    result = await registry._unregister_by_pid(pid)

    assert result is True
    # Allow the background task created by asyncio.create_task to run
    await asyncio.sleep(0)  # yield control once
    # Could also wait with asyncio.wait([...]) if we had the task reference

    # Verify release_adapter_tunnels was called with the adapter instance
    mock_allocator.release_adapter_tunnels.assert_awaited_once_with(adapter)
    # Verify adapter removed from registry
    assert pid not in registry._by_pid
    assert ('dummy', 'testsession') not in registry.adapters


@pytest.mark.asyncio
async def test_unregister_by_pid_without_resource_allocator(registry):
    """Test that _unregister_by_pid works even if no resource allocator set."""
    # No allocator set
    fake_process = MagicMock(spec=asyncio.subprocess.Process)
    adapter = AdapterInstance(
        adapter_type='dummy',
        session_name='testsession',
        process=fake_process,
        control_socket='/tmp/test.sock'
    )
    pid = 12345
    async with registry._lock:
        registry._by_pid[pid] = adapter
        registry.adapters[('dummy', 'testsession')] = adapter

    result = await registry._unregister_by_pid(pid)
    assert result is True
    assert pid not in registry._by_pid


@pytest.mark.asyncio
async def test_unregister_by_pid_nonexistent(registry):
    """Test _unregister_by_pid returns False for unknown pid."""
    result = await registry._unregister_by_pid(99999)
    assert result is False
