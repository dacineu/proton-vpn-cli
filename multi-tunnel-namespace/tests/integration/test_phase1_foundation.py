"""Integration tests for Phase 1 foundation."""

import sys
from pathlib import Path
import asyncio
import pytest
import os

# Ensure src is in sys.path for imports
SRC_PATH = Path(__file__).parent.parent / "src"
if str(SRC_PATH) not in sys.path:
    sys.path.insert(0, str(SRC_PATH))

from libvpnmanager.client import ManagerClient, AdapterClient
from libvpnmanager.models.config import ConnectionConfig
from libvpnmanager.models.exceptions import TunnelError

pytestmark = pytest.mark.integration


@pytest.mark.asyncio
async def test_adapter_startup(manager_client):
    """Test adapter startup via start_adapter."""
    creds = {'username': 'testuser', 'password': 'testpass'}
    # Verify 2FA to get session token
    totp_result = await manager_client.verify_2fa('123456')
    session_token = totp_result.get('session_token')
    assert session_token is not None, "Session token should be returned"

    # Start adapter
    endpoint = await manager_client.start_adapter('dummy', creds, session_token=session_token)
    assert endpoint.startswith('unix://'), f"Endpoint should start with unix://, got {endpoint}"
    socket_path = endpoint.replace('unix://', '')
    socket_file = Path(socket_path)
    assert socket_file.exists(), f"Socket file {socket_path} should exist"

    # Check socket permissions (should be 0600)
    import stat
    mode = stat.S_IMODE(socket_file.stat().st_mode)
    assert mode == 0o600, f"Expected socket mode 0600, got {oct(mode)}"

    # Verify adapter appears in list_adapters
    adapters = await manager_client.list_adapters()
    # Find an entry with adapter_type='dummy' and username='testuser'
    found = any(
        isinstance(a, dict) and a.get('adapter_type') == 'dummy' and a.get('username') == 'testuser'
        for a in adapters
    )
    assert found, "Dummy adapter for testuser not found in list_adapters"


@pytest.mark.asyncio
async def test_create_tunnel(manager_client):
    """Test tunnel creation via AdapterClient."""
    creds = {'username': 'testuser', 'password': 'testpass'}
    totp_result = await manager_client.verify_2fa('123456')
    session_token = totp_result['session_token']
    endpoint = await manager_client.start_adapter('dummy', creds, session_token=session_token)

    async with AdapterClient(endpoint, session_token=session_token) as adapter:
        config = ConnectionConfig(adapter='dummy', tunnel_name='tunnel1')
        tunnel = await adapter.create_tunnel('tunnel1', config)
        assert tunnel.name == 'tunnel1'
        assert tunnel.adapter == 'dummy'
        assert tunnel.device.startswith('dummy')
        assert tunnel.namespace.startswith('vpn_')


@pytest.mark.asyncio
async def test_concurrent_connections(manager_client):
    """Test concurrent connections to the same adapter."""
    creds = {'username': 'testuser', 'password': 'testpass'}
    totp_result = await manager_client.verify_2fa('123456')
    session_token = totp_result['session_token']
    endpoint = await manager_client.start_adapter('dummy', creds, session_token=session_token)

    async with AdapterClient(endpoint, session_token=session_token) as adapter1:
        async with AdapterClient(endpoint, session_token=session_token) as adapter2:
            config1 = ConnectionConfig(adapter='dummy', tunnel_name='conc1')
            config2 = ConnectionConfig(adapter='dummy', tunnel_name='conc2')
            results = await asyncio.gather(
                adapter1.create_tunnel('conc1', config1),
                adapter2.create_tunnel('conc2', config2),
            )
            assert len(results) == 2
            assert results[0].name == 'conc1'
            assert results[1].name == 'conc2'
            # Verify both tunnels are listed
            tunnels = await adapter1.list_tunnels()
            assert len(tunnels) == 2
            tunnel_names = {t.name for t in tunnels}
            assert 'conc1' in tunnel_names
            assert 'conc2' in tunnel_names


@pytest.mark.asyncio
async def test_token_validation(manager_client):
    """Test that invalid session token is rejected."""
    creds = {'username': 'testuser', 'password': 'testpass'}
    totp_result = await manager_client.verify_2fa('123456')
    session_token = totp_result['session_token']
    endpoint = await manager_client.start_adapter('dummy', creds, session_token=session_token)

    # Try with invalid token
    adapter_bad = AdapterClient(endpoint, session_token='invalidtoken')
    with pytest.raises(TunnelError) as exc_info:
        # Need to connect and attempt operation
        await adapter_bad.connect()
        config = ConnectionConfig(adapter='dummy', tunnel_name='badtest')
        await adapter_bad.create_tunnel('badtest', config)
    assert 'INVALID_SESSION' in str(exc_info.value)
    await adapter_bad.disconnect()

    # Valid token should succeed
    async with AdapterClient(endpoint, session_token=session_token) as adapter_good:
        config = ConnectionConfig(adapter='dummy', tunnel_name='goodtest')
        tunnel = await adapter_good.create_tunnel('goodtest', config)
        assert tunnel.name == 'goodtest'


@pytest.mark.asyncio
async def test_phase1_success_criteria(manager_client):
    """End-to-end smoke test covering all Phase 1 success criteria."""
    # 1. Adapter startup
    creds = {'username': 'testuser', 'password': 'testpass'}
    totp_result = await manager_client.verify_2fa('123456')
    session_token = totp_result['session_token']
    endpoint = await manager_client.start_adapter('dummy', creds, session_token=session_token)
    assert endpoint.startswith('unix://')
    socket_path = endpoint.replace('unix://', '')
    assert Path(socket_path).exists()
    import stat
    mode = stat.S_IMODE(Path(socket_path).stat().st_mode)
    assert mode == 0o600
    adapters = await manager_client.list_adapters()
    assert any(
        isinstance(a, dict) and a.get('adapter_type') == 'dummy' and a.get('username') == 'testuser'
        for a in adapters
    )

    # 2. Tunnel creation via AdapterClient
    async with AdapterClient(endpoint, session_token=session_token) as adapter:
        config = ConnectionConfig(adapter='dummy', tunnel_name='tunnel1')
        tunnel = await adapter.create_tunnel('tunnel1', config)
        assert tunnel.name == 'tunnel1'
        assert tunnel.adapter == 'dummy'
        assert tunnel.device.startswith('dummy')
        assert tunnel.namespace.startswith('vpn_')

    # 3. Concurrent connections
    async with AdapterClient(endpoint, session_token=session_token) as adapter1:
        async with AdapterClient(endpoint, session_token=session_token) as adapter2:
            config1 = ConnectionConfig(adapter='dummy', tunnel_name='conc1')
            config2 = ConnectionConfig(adapter='dummy', tunnel_name='conc2')
            results = await asyncio.gather(
                adapter1.create_tunnel('conc1', config1),
                adapter2.create_tunnel('conc2', config2),
            )
            assert len(results) == 2
            assert results[0].name == 'conc1'
            assert results[1].name == 'conc2'
            tunnels = await adapter1.list_tunnels()
            assert len(tunnels) == 2

    # 4. Token validation
    adapter_bad = AdapterClient(endpoint, session_token='bad')
    with pytest.raises(TunnelError) as exc:
        config = ConnectionConfig(adapter='dummy', tunnel_name='badtest')
        await adapter_bad.create_tunnel('badtest', config)
    assert 'INVALID_SESSION' in str(exc.value)
    await adapter_bad.disconnect()
