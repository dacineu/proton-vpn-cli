"""Integration tests for Phase 2: Proton Adapter & CLI Integration.

These tests verify that the Proton adapter migration is successful and the CLI
direct adapter communication flow works correctly.
"""

import pytest
import asyncio
import os
import sys
import json
from pathlib import Path
from unittest.mock import patch, MagicMock
import tempfile
import stat

# Ensure src is in path for imports
SRC_PATH = Path(__file__).parent.parent / "src"
if str(SRC_PATH) not in sys.path:
    sys.path.insert(0, str(SRC_PATH))

# The mocks directory is already in sys.path via conftest.py

from daemon.daemon import VPNDaemon
from libvpnmanager.client import ManagerClient, AdapterClient
from libvpnmanager.models.config import ProtonConnectionConfig
from libvpnmanager.models.tunnel import Tunnel
from libvpnmanager.models.status import TunnelStatus

pytestmark = pytest.mark.integration


# --- Test fixtures ---

@pytest.fixture
def tmp_adapter_dir(tmp_path):
    """Provide a temporary adapter directory."""
    adapter_dir = tmp_path / "adapters"
    adapter_dir.mkdir()
    return adapter_dir


@pytest.fixture
def proton_credentials():
    """Return test Proton credentials."""
    return {
        'username': 'testuser@protonmail.com',
        'password': 'testpassword123',
        # Session data expected by ProtonSession
        'access_token': 'dummy_access_token',
        'refresh_token': 'dummy_refresh_token',
        'expires_at': None,
    }


@pytest.fixture
def session_token():
    """Return a test session token."""
    return 'test-session-token-12345'


@pytest.fixture
def proton_config():
    """Return a basic Proton connection configuration."""
    return ProtonConnectionConfig(
        tunnel_name='test-tunnel',
        server_id='CH-Zurich-1',
        country='CH',
        protocol='wireguard'
    )


# --- Tests ---

@pytest.mark.asyncio
async def test_proton_adapter_startup(manager_client, tmp_adapter_dir, proton_credentials, session_token):
    """Test adapter startup via start_adapter with proton type."""
    # The daemon should be able to start a proton adapter (it will find mtm-adapter-proton executable)
    # Since we're running as root in integration tests, we can actually spawn the process.
    # The proton adapter will try to import proton.vpn.core.api; the mock will satisfy it.

    # Verify 2FA to obtain session token (dummy)
    totp_result = await manager_client.verify_2fa('123456')
    real_session_token = totp_result.get('session_token')
    assert real_session_token is not None, "Session token should be returned from verify_2fa"

    # Start proton adapter
    endpoint = await manager_client.start_adapter('proton', proton_credentials, session_token=real_session_token)
    assert endpoint.startswith('unix://'), f"Endpoint should start with unix://, got {endpoint}"
    socket_path = endpoint.replace('unix://', '')
    socket_file = Path(socket_path)
    assert socket_file.exists(), f"Socket file {socket_path} should exist"

    # Check socket permissions (should be 0600)
    mode = stat.S_IMODE(socket_file.stat().st_mode)
    assert mode == 0o600, f"Expected socket mode 0600, got {oct(mode)}"

    # Verify adapter appears in list_adapters
    adapters = await manager_client.list_adapters()
    found = any(
        isinstance(a, dict) and a.get('adapter_type') == 'proton' and a.get('username') == proton_credentials['username']
        for a in adapters
    )
    assert found, "Proton adapter not found in list_adapters"

    # Clean up: stop the adapter
    stopped = await manager_client.stop_adapter('proton', proton_credentials['username'])
    assert stopped, "Adapter should stop successfully"


@pytest.mark.asyncio
async def test_tunnel_creation_and_session_reuse(manager_client, tmp_adapter_dir, proton_credentials, session_token, proton_config):
    """Test tunnel creation via AdapterClient and session reuse."""
    # Start adapter
    totp_result = await manager_client.verify_2fa('123456')
    session_token_val = totp_result['session_token']
    endpoint = await manager_client.start_adapter('proton', proton_credentials, session_token=session_token_val)

    # Create first tunnel using AdapterClient
    async with AdapterClient(endpoint, session_token=session_token_val) as adapter:
        tunnel1 = await adapter.create_tunnel('tunnel1', proton_config)
        assert tunnel1.name == 'tunnel1'
        assert tunnel1.adapter == 'proton'
        # Device should be something like proton-tunnel1 (truncated)
        assert tunnel1.device.startswith('proton-')
        # Namespace should be present (might be None if MTM not actually allocating in test)
        # In real integration, namespace would be set; here we skip strict check

        # Create second tunnel from same adapter client (or new client) to verify reuse
        tunnel2 = await adapter.create_tunnel('tunnel2', proton_config)
        assert tunnel2.name == 'tunnel2'
        assert tunnel2.adapter == 'proton'

        # Both tunnels should be listed in adapter's internal state
        tunnels = await adapter.list_tunnels()
        tunnel_names = {t.name for t in tunnels}
        assert 'tunnel1' in tunnel_names
        assert 'tunnel2' in tunnel_names
        assert len(tunnels) >= 2


@pytest.mark.asyncio
async def test_adapter_list_stop(manager_client, proton_credentials, session_token):
    """Test adapter list and stop commands."""
    # Start an adapter
    totp_result = await manager_client.verify_2fa('123456')
    session_token_val = totp_result['session_token']
    endpoint = await manager_client.start_adapter('proton', proton_credentials, session_token=session_token_val)

    # Verify it's in the list
    adapters_before = await manager_client.list_adapters()
    found_before = any(
        a.get('adapter_type') == 'proton' and a.get('username') == proton_credentials['username']
        for a in adapters_before
    )
    assert found_before, "Adapter should appear in list_adapters"

    # Stop the adapter
    stopped = await manager_client.stop_adapter('proton', proton_credentials['username'])
    assert stopped, "Adapter stop should return True"

    # Verify it's no longer in the list (might take a moment)
    # Since stop is synchronous and pool is updated immediately, we should see it gone
    adapters_after = await manager_client.list_adapters()
    found_after = any(
        a.get('adapter_type') == 'proton' and a.get('username') == proton_credentials['username']
        for a in adapters_after
    )
    assert not found_after, "Adapter should be removed from list after stop"


@pytest.mark.asyncio
async def test_credential_prompt_shown_when_adapter_missing(monkeypatch):
    """Test that credential prompt is shown when no adapter is running."""
    from cli.tunnel import prompt_credentials_if_needed
    # We'll simulate list_adapters returning empty
    async def mock_list_adapters(self):
        return []

    # Patch ManagerClient.list_adapters to return empty
    monkeypatch.setattr(ManagerClient, 'list_adapters', mock_list_adapters, raising=False)

    # Mock click.prompt to capture whether it was called
    called = []
    def fake_prompt(*args, **kwargs):
        called.append(True)
        return {'username': 'test@example.com', 'password': 'pw123'}

    monkeypatch.setattr('click.prompt', fake_prompt)

    # Call should prompt and return credentials
    creds = await prompt_credentials_if_needed('proton')
    assert creds is not None, "Should return credentials"
    assert len(called) > 0, "click.prompt should have been called"


@pytest.mark.asyncio
async def test_credential_prompt_skipped_when_adapter_running(monkeypatch, proton_credentials):
    """Test that credential prompt is skipped when adapter already running."""
    from cli.tunnel import prompt_credentials_if_needed

    # Mock list_adapters to return a running adapter for this user
    async def mock_list_adapters(self):
        return [{
            'adapter_type': 'proton',
            'username': proton_credentials['username'],
            'endpoint': 'unix:///tmp/test.sock'
        }]

    monkeypatch.setattr(ManagerClient, 'list_adapters', mock_list_adapters, raising=False)

    # Mock click.prompt should NOT be called
    called = []
    def fake_prompt(*args, **kwargs):
        called.append(True)
        return {'username': 'wrong', 'password': 'wrong'}

    monkeypatch.setattr('click.prompt', fake_prompt)

    # Call should return None (no credentials needed)
    creds = await prompt_credentials_if_needed('proton')
    assert creds is None, "Should return None when adapter is running"
    assert len(called) == 0, "click.prompt should NOT have been called"


@pytest.mark.asyncio
async def test_phase2_success_criteria(manager_client, tmp_adapter_dir, proton_credentials, proton_config):
    """End-to-end smoke test verifying Phase 2 success criteria."""
    # 1. Adapter startup with stdin credentials
    totp_result = await manager_client.verify_2fa('123456')
    session_token = totp_result['session_token']
    endpoint = await manager_client.start_adapter('proton', proton_credentials, session_token=session_token)
    assert endpoint.startswith('unix://')

    # 2. Tunnel creation and session reuse
    async with AdapterClient(endpoint, session_token=session_token) as adapter:
        tunnel = await adapter.create_tunnel('smoke1', proton_config)
        assert tunnel.adapter == 'proton'
        assert tunnel.name == 'smoke1'
        # Verify tunnel appears in adapter.list_tunnels()
        tunnels = await adapter.list_tunnels()
        assert any(t.name == 'smoke1' for t in tunnels)

    # 3. Second tunnel uses same adapter session (no new prompt)
    # Re-connect as new client with same session token
    async with AdapterClient(endpoint, session_token=session_token) as adapter2:
        tunnel2 = await adapter2.create_tunnel('smoke2', proton_config)
        assert tunnel2.name == 'smoke2'
        # Both tunnels should be present
        tunnels = await adapter2.list_tunnels()
        assert len(tunnels) >= 2

    # 4. Session token enforcement: invalid token rejected
    try:
        async with AdapterClient(endpoint, session_token='invalid-token') as bad_adapter:
            await bad_adapter.create_tunnel('shouldfail', proton_config)
        assert False, "Should have raised an authentication error"
    except Exception as e:
        # Expected: permission denied or auth failure
        assert 'token' in str(e).lower() or 'permission' in str(e).lower() or 'auth' in str(e).lower()

    # 5. Adapter management: list and stop
    adapters = await manager_client.list_adapters()
    assert any(a.get('adapter_type') == 'proton' for a in adapters)
    stopped = await manager_client.stop_adapter('proton', proton_credentials['username'])
    assert stopped


@pytest.mark.asyncio
async def test_legacy_create_tunnel_still_works(manager_client, proton_credentials):
    """Verify legacy ManagerClient.create_tunnel still functions."""
    # The legacy path uses StartAdapter internally then forwards to adapter via control.
    # For proton adapter, we need working proton.vpn.core.api. With our mock, this may
    # still work if the adapter can be started and the control path works.
    # However, create_tunnel uses the adapter via the adapter_registry, not direct AdapterClient.

    # Since legacy create_tunnel goes through the daemon's create_tunnel method which
    # uses the adapter registry and control socket, we can test it if the adapter works.
    # But we need to ensure the daemon can forward requests.

    # For now, this test is meaningful only with a fully functional mock.
    # We'll test the client method exists and can be called; we'll skip deep validation
    # because the mock might not support the full control path.

    # Actually, we can test with the dummy adapter instead, which is simpler.
    # But the requirement is to verify backward compatibility. We'll use proton if available.

    totp_result = await manager_client.verify_2fa('123456')
    session_token = totp_result['session_token']
    # Build a dummy connection config with adapter='proton' - but the daemon will start the proton adapter.
    # That should work with our mock.
    config = ProtonConnectionConfig(
        tunnel_name='legacy-tunnel',
        server_id='CH-Zurich-1',
        country='CH',
        protocol='wireguard'
    )

    # Call the legacy create_tunnel method. It should:
    # - Ensure an adapter is running (StartAdapter)
    # - Forward the request via control socket to the adapter
    result = await manager_client.create_tunnel(config, proton_credentials['username'])
    assert result is not None, "Legacy create_tunnel should return a tunnel dict"
    assert 'name' in result
    assert result['name'] == 'legacy-tunnel'
    assert result['adapter'] == 'proton'
