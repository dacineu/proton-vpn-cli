"""Unit tests for NetworkNamespaceRouting."""

import pytest
import asyncio
from unittest.mock import patch, AsyncMock

from libvpnmanager.routing import NetworkNamespaceRouting
from libvpnmanager.models.exceptions import (
    NamespaceExistsError,
    NamespaceNotFoundError,
    DeviceNotFoundError,
)


@pytest.fixture
def routing():
    return NetworkNamespaceRouting()


@pytest.mark.asyncio
async def test_create_namespace(routing):
    """Test namespace creation."""
    # Mock the command runner
    with patch.object(routing, "_run_command") as mock_run:
        # First call: ip netns list returns empty
        mock_run.return_value = type(
            "Result", (), {"stdout": "", "returncode": 0}
        )()

        ns_name = await routing.create_namespace("test_tunnel")

        assert ns_name == "vpn_test_tunnel"
        assert routing._namespaces["test_tunnel"] == "vpn_test_tunnel"

        # Verify command called
        mock_run.assert_called_with(["ip", "netns", "add", "vpn_test_tunnel"])


@pytest.mark.asyncio
async def test_namespace_already_exists(routing):
    """Test error when namespace already exists."""
    routing._namespaces["test"] = "vpn_test"

    with patch.object(routing, "_list_namespaces", return_value={"vpn_test"}):
        with pytest.raises(NamespaceExistsError):
            await routing.create_namespace("test")


@pytest.mark.asyncio
async def test_destroy_namespace(routing):
    """Test namespace destruction."""
    routing._namespaces["test"] = "vpn_test"
    routing._tunnels_in_ns["vpn_test"] = set()

    with patch.object(routing, "_run_command") as mock_run:
        await routing.destroy_tunnel_context("test", {})

        mock_run.assert_called_with(["ip", "netns", "delete", "vpn_test"], check=False)
        assert "test" not in routing._namespaces
        assert "vpn_test" not in routing._tunnels_in_ns


@pytest.mark.asyncio
async def test_list_active_tunnels(routing):
    """Test listing active tunnel contexts."""
    routing._namespaces["tunnel1"] = "vpn_tunnel1"
    routing._namespaces["tunnel2"] = "vpn_tunnel2"

    result = await routing.list_active_tunnels()

    assert result == {
        "tunnel1": {"namespace": "vpn_tunnel1"},
        "tunnel2": {"namespace": "vpn_tunnel2"},
    }


@pytest.mark.asyncio
async def test_cleanup_all(routing):
    """Test cleanup on shutdown."""
    routing._namespaces["t1"] = "vpn_t1"
    routing._namespaces["t2"] = "vpn_t2"
    routing._tunnels_in_ns["vpn_t1"] = set()
    routing._tunnels_in_ns["vpn_t2"] = set()

    with patch.object(routing, "destroy_tunnel_context", new_callable=AsyncMock) as mock_destroy:
        await routing.cleanup_all()

        assert mock_destroy.call_count == 2
        routing._namespaces.clear()
        routing._tunnels_in_ns.clear()
