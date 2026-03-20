"""Unit tests for adapter idle timeout (DAEM-06)."""

import pytest
import asyncio
from unittest.mock import MagicMock, AsyncMock
from daemon.adapter_registry import AdapterRegistry, AdapterInstance


@pytest.fixture
def registry():
    """Create a fresh AdapterRegistry with a short idle timeout for tests."""
    reg = AdapterRegistry(adapter_dir="/tmp/test_adapters", idle_timeout=1.0)
    return reg


@pytest.mark.asyncio
async def test_check_idle_adapters_terminates_idle(registry):
    """Test that _check_idle_adapters terminates adapters exceeding idle timeout."""
    # Mock terminate_adapter
    terminated = []
    async def mock_terminate(adapter_type, session_name):
        terminated.append((adapter_type, session_name))
        return True
    registry.terminate_adapter = mock_terminate

    # Create an adapter with last_used far in the past
    now = asyncio.get_event_loop().time()
    old_time = now - 5.0  # 5 seconds ago
    fake_process = MagicMock(spec=asyncio.subprocess.Process)
    adapter = AdapterInstance(
        adapter_type='dummy',
        session_name='idle_session',
        process=fake_process,
        control_socket='/tmp/idle.sock',
        last_used=old_time
    )
    async with registry._lock:
        registry.adapters[('dummy', 'idle_session')] = adapter

    # Run check
    await registry._check_idle_adapters()

    assert ('dummy', 'idle_session') in terminated


@pytest.mark.asyncio
async def test_check_idle_adapters_does_not_terminate_recent(registry):
    """Test that adapters used recently are not terminated."""
    terminated = []
    async def mock_terminate(adapter_type, session_name):
        terminated.append((adapter_type, session_name))
        return True
    registry.terminate_adapter = mock_terminate

    # Create an adapter with recent last_used
    now = asyncio.get_event_loop().time()
    recent_time = now - 0.1  # 0.1 seconds ago, within 1.0 timeout
    fake_process = MagicMock(spec=asyncio.subprocess.Process)
    adapter = AdapterInstance(
        adapter_type='dummy',
        session_name='recent_session',
        process=fake_process,
        control_socket='/tmp/recent.sock',
        last_used=recent_time
    )
    async with registry._lock:
        registry.adapters[('dummy', 'recent_session')] = adapter

    await registry._check_idle_adapters()

    assert ('dummy', 'recent_session') not in terminated


@pytest.mark.asyncio
async def test_set_idle_timeout(registry):
    """Test set_idle_timeout updates the timeout."""
    assert registry._idle_timeout == 1.0
    registry.set_idle_timeout(120.0)
    assert registry._idle_timeout == 120.0
