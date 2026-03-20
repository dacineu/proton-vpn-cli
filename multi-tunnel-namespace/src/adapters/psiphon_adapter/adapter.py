"""Psiphon VPN adapter for libvpnmanager."""

import asyncio
import logging
from typing import Dict, Optional

from libvpnmanager.adapters.base import VPNAdapter, AdapterCapabilities
from libvpnmanager.models.tunnel import Tunnel
from libvpnmanager.models.status import TunnelStatus
from libvpnmanager.models.exceptions import ConnectionError, TunnelNotFoundError

logger = logging.getLogger(__name__)


class PsiphonAdapter(VPNAdapter):
    """Psiphon VPN adapter implementation."""

    def __init__(self, session=None):
        """
        Initialize adapter.

        Args:
            session: PsiphonSession instance (optional, for credentials/config)
        """
        self.session = session
        self._tunnel_procs: Dict[str, asyncio.subprocess.Process] = {}

    @property
    def capabilities(self) -> AdapterCapabilities:
        return AdapterCapabilities(
            multi_tunnel=True,
            supports_protocols=["tcp", "udp", "ssh"],
            max_tunnels=None,
            supports_per_app_routing=False,
            supports_kill_switch=False,
            supports_dns_isolation=True,
        )

    async def connect(
        self,
        config,
        progress_callback: Optional[callable] = None,
    ):
        if progress_callback:
            progress_callback("Starting Psiphon...")

        tunnel_name = config.tunnel_name
        try:
            proc = await asyncio.create_subprocess_exec(
                "psiphon",
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
            )
            self._tunnel_procs[tunnel_name] = proc

            if progress_callback:
                progress_callback("Psiphon connecting...")

            tunnel = Tunnel(
                name=tunnel_name,
                adapter="psiphon",
                session_name=config.session_name,
                username=config.username,
                device="127.0.0.1:1080",
                namespace=None,
                endpoint=None,
                metadata={"pid": proc.pid},
            )
            return tunnel
        except Exception as e:
            raise ConnectionError(f"Psiphon connection failed: {e}") from e

    async def disconnect(self, tunnel):
        proc = self._tunnel_procs.get(tunnel.name)
        if proc:
            try:
                proc.terminate()
                await proc.wait()
            except Exception as e:
                logger.warning(f"Error stopping Psiphon: {e}")
            self._tunnel_procs.pop(tunnel.name, None)

    async def get_status(self, tunnel) -> TunnelStatus:
        proc = self._tunnel_procs.get(tunnel.name)
        if not proc:
            return TunnelStatus.DISCONNECTED
        try:
            proc.wait(timeout=0)
            return TunnelStatus.DISCONNECTED
        except asyncio.TimeoutError:
            return TunnelStatus.CONNECTED
        except Exception:
            return TunnelStatus.ERROR

    async def get_traffic_stats(self, tunnel):
        return (0, 0)

    async def list_tunnels(self) -> List[Tunnel]:
        """List all active Psiphon tunnels."""
        tunnels = []
        for tunnel_name, proc in self._tunnel_procs.items():
            # Reconstruct minimal Tunnel info
            tunnel = Tunnel(
                name=tunnel_name,
                adapter="psiphon",
                session_name="",  # not stored separately
                username="",
                device="127.0.0.1:1080",
                namespace=None,
                endpoint=None,
                metadata={"pid": proc.pid},
            )
            tunnels.append(tunnel)
        return tunnels

    async def get_capabilities(self) -> AdapterCapabilities:
        """Return Psiphon adapter capabilities."""
        return self.capabilities

    async def cleanup(self):
        for proc in self._tunnel_procs.values():
            try:
                proc.terminate()
                await proc.wait()
            except Exception:
                pass
        self._tunnel_procs.clear()
