"""Dummy adapter for testing and development."""

import asyncio
import logging
from datetime import datetime
from typing import Optional, Tuple

from libvpnmanager.adapters.base import VPNAdapter, AdapterCapabilities
from libvpnmanager.models.tunnel import Tunnel
from libvpnmanager.models.status import TunnelStatus


logger = logging.getLogger(__name__)


class DummyAdapter(VPNAdapter):
    """Dummy VPN adapter for testing.

    This adapter simulates a VPN connection without actually doing anything.
    Useful for testing the manager and daemon without needing real VPN services.
    """

    def __init__(self, session=None):
        self.session = session
        self._tunnels: Dict[str, Tunnel] = {}

    @property
    def capabilities(self) -> AdapterCapabilities:
        return AdapterCapabilities(
            multi_tunnel=True,
            supports_protocols=["dummy"],
            max_tunnels=None,
            supports_per_app_routing=False,
            supports_kill_switch=False,
            supports_dns_isolation=False,
        )

    async def connect(
        self,
        config,
        progress_callback: Optional[callable] = None,
    ) -> Tunnel:
        """Simulate connecting a dummy tunnel."""
        tunnel_name = config.tunnel_name
        logger.info(f"Dummy connect: {tunnel_name}")

        if progress_callback:
            progress_callback("Starting dummy tunnel...")

        await asyncio.sleep(0.5)  # Simulate work

        if progress_callback:
            progress_callback("Dummy tunnel connected")

        username = self.session.username if self.session else ""
        tunnel = Tunnel(
            name=tunnel_name,
            adapter="dummy",
            session_name=config.session_name,
            username=username,
            device=f"dum-{tunnel_name}",  # Fake device name
            namespace=None,
            endpoint="127.0.0.1:0",
            connected_at=datetime.now(),
            gateway="10.8.0.1",  # dummy gateway
            dns_servers=["1.1.1.1", "1.0.0.1"],  # dummy DNS
            vpn_ip="10.8.0.2",  # dummy client IP
            metadata={"simulated": True},
        )
        self._tunnels[tunnel_name] = tunnel
        return tunnel

    async def disconnect(self, tunnel: Tunnel):
        """Simulate disconnecting."""
        tunnel_name = tunnel.name
        if tunnel_name in self._tunnels:
            self._tunnels.pop(tunnel_name)
            logger.info(f"Dummy disconnect: {tunnel_name}")

    async def get_status(self, tunnel: Tunnel) -> TunnelStatus:
        """Return status."""
        if tunnel.name in self._tunnels:
            return TunnelStatus.CONNECTED
        return TunnelStatus.DISCONNECTED

    async def get_traffic_stats(self, tunnel: Tunnel) -> Tuple[int, int]:
        """Return fake stats."""
        return (123456, 789012)

    async def list_tunnels(self) -> List[Tunnel]:
        """List all tunnels."""
        return list(self._tunnels.values())

    async def get_capabilities(self) -> AdapterCapabilities:
        """Return capabilities."""
        return AdapterCapabilities(
            multi_tunnel=True,
            supports_protocols=["dummy"],
            max_tunnels=None,
            supports_per_app_routing=False,
            supports_kill_switch=False,
            supports_dns_isolation=False,
        )

    async def cleanup(self):
        """Clean up all tunnels."""
        self._tunnels.clear()
        logger.info("Dummy adapter cleaned up")
