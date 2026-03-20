"""Integration tests for Phase 2: Proton Adapter & CLI Integration."""

import pytest
from unittest.mock import patch

pytestmark = pytest.mark.integration

# NOTE: Full tests require proton.vpn.core.api to be available or properly mocked.
# For now, these tests are skeletons; they will be implemented when the mock is ready.


@pytest.mark.asyncio
async def test_proton_adapter_startup(manager_client):
    """Test adapter startup with stdin credentials."""
    pytest.skip("Proton core API mock not implemented")


@pytest.mark.asyncio
async def test_tunnel_creation_and_session_reuse(manager_client):
    """Test tunnel creation and session reuse."""
    pytest.skip("Proton core API mock not implemented")


@pytest.mark.asyncio
async def test_adapter_list_stop(manager_client):
    """Test adapter list and stop commands."""
    pytest.skip("Proton core API mock not implemented")


@pytest.mark.asyncio
async def test_credential_prompt_shown_when_adapter_missing():
    """Test that credential prompt is shown when no adapter running."""
    pytest.skip("Proton core API mock not implemented")


@pytest.mark.asyncio
async def test_credential_prompt_skipped_when_adapter_running():
    """Test that credential prompt is skipped when adapter already running."""
    pytest.skip("Proton core API mock not implemented")


@pytest.mark.asyncio
async def test_phase2_success_criteria(manager_client):
    """End-to-end smoke test verifying Phase 2 success criteria."""
    pytest.skip("Proton core API mock not implemented")


@pytest.mark.asyncio
async def test_legacy_create_tunnel_still_works(manager_client):
    """Verify legacy ManagerClient.create_tunnel still works."""
    pytest.skip("Legacy API test pending")
