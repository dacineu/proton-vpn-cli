"""Dummy adapter for testing and development."""

import asyncio
from datetime import datetime
from typing import List, Tuple, Optional

from ..models.tunnel import Tunnel
from ..models.status import TunnelStatus
from ..models.config import ConnectionConfig
from .base import VPNAdapter, AdapterCapabilities
from ..models.exceptions import (
    TunnelNotFoundError,
    ConfigurationError,
    ConnectionError,
)


class DummyAdapter(VPNAdapter):
    """
    Dummy adapter for testing.

    Creates fake TUN devices (actually just regular files or /dev/null)
    and simulates connection states. For testing only.
    """

    def __init__(self):
        self._tunnels: List[Tunnel] = []
        self._counter = 0

    async def connect(
        self,
        config: ConnectionConfig,
        progress_callback: Optional[callable] = None,
    ) -> Tunnel:
        """Simulate connecting a dummy tunnel."""
        if progress_callback:
            progress_callback("connecting")

        await asyncio.sleep(0.5)  # Simulate connection delay

        self._counter += 1
        device = f"dummy{self._counter}"

        tunnel = Tunnel(
            name=config.tunnel_name,
            adapter=self.get_adapter_name(),
            device=device,
            namespace=f"vpn_{config.tunnel_name}",
            endpoint="dummy.example.com",
            connected_at=datetime.utcnow(),
            metadata={"dummy": True, "device_index": self._counter},
        )
        self._tunnels.append(tunnel)

        if progress_callback:
            progress_callback("connected")

        return tunnel

    async def disconnect(self, tunnel: Tunnel) -> None:
        """Simulate disconnecting."""
        # Find by name (different instance than stored)
        for i, t in enumerate(self._tunnels):
            if t.name == tunnel.name:
                self._tunnels.pop(i)
                return
        raise TunnelNotFoundError(f"Tunnel {tunnel.name} not found")

    async def get_status(self, tunnel: Tunnel) -> TunnelStatus:
        """Return status based on whether tunnel is in our list."""
        if tunnel in self._tunnels:
            return TunnelStatus.CONNECTED
        return TunnelStatus.DISCONNECTED

    def list_tunnels(self) -> List[Tunnel]:
        """Return all tunnels."""
        return list(self._tunnels)

    def get_capabilities(self) -> AdapterCapabilities:
        """Dummy supports multi-tunnel for testing."""
        return AdapterCapabilities(
            multi_tunnel=True,
            supports_protocols=["dummy"],
            max_tunnels=None,
            supports_per_app_routing=True,
            supports_kill_switch=False,
            supports_dns_isolation=False,
        )

    async def get_traffic_stats(
        self, tunnel: Tunnel
    ) -> Tuple[int, int]:
        """Return dummy stats."""
        # Find tunnel by name (since tunnel objects may be different instances)
        for t in self._tunnels:
            if t.name == tunnel.name:
                return [12345, 67890]  # Return as list for D-Bus struct
        raise TunnelNotFoundError(f"Tunnel {tunnel.name} not found")

    async def cleanup(self) -> None:
        """Clean up all tunnels."""
        self._tunnels.clear()
