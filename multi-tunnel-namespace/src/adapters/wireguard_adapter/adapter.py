"""WireGuard VPN adapter for libvpnmanager."""

import asyncio
import logging
import subprocess
from typing import Dict, Optional, List

from libvpnmanager.adapters.base import VPNAdapter, AdapterCapabilities
from libvpnmanager.models.tunnel import Tunnel
from libvpnmanager.models.status import TunnelStatus
from libvpnmanager.models.config import WireGuardConnectionConfig
from libvpnmanager.models.exceptions import ConnectionError, ConfigurationError

logger = logging.getLogger(__name__)


class WireGuardAdapter(VPNAdapter):
    """WireGuard VPN adapter implementation."""

    def __init__(self, session=None):
        """
        Initialize adapter.

        Args:
            session: WireGuardSession instance (optional, contains config file)
        """
        self.session = session
        self._tunnels: Dict[str, Dict] = {}

    @property
    def capabilities(self) -> AdapterCapabilities:
        return AdapterCapabilities(
            multi_tunnel=True,
            supports_protocols=["wireguard"],
            max_tunnels=None,
            supports_per_app_routing=False,
            supports_kill_switch=False,
            supports_dns_isolation=False,
        )

    async def connect(
        self,
        config: WireGuardConnectionConfig,
        progress_callback: Optional[callable] = None,
    ):
        """Connect WireGuard tunnel."""
        if progress_callback:
            progress_callback("Configuring WireGuard...")

        tunnel_name = config.tunnel_name

        try:
            # WireGuard config can be provided directly as strings
            interface_name = f"wg-{tunnel_name}"

            # Create WireGuard config file in /etc/wireguard/ or run via wg-quick
            config_content = f"""[Interface]
PrivateKey = {config.private_key}
Address = {config.address}
DNS = {config.dns if config.dns else '1.1.1.1'}

[Peer]
PublicKey = {config.peer_public_key}
Endpoint = {config.endpoint}
AllowedIPs = {', '.join(config.allowed_ips) if config.allowed_ips else '0.0.0.0/0'}
PersistentKeepalive = 25
"""
            config_path = f"/etc/wireguard/{interface_name}.conf"

            # Write config (would need root)
            # In production, this daemon runs as root so it can write
            with open(config_path, "w") as f:
                f.write(config_content)

            # Bring up interface
            proc = await asyncio.create_subprocess_exec(
                "wg-quick", "up", interface_name,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
            )
            stdout, stderr = await proc.communicate()

            if proc.returncode != 0:
                raise ConfigurationError(f"wg-quick up failed: {stderr.decode()}")

            if progress_callback:
                progress_callback("WireGuard connected")

            tunnel = Tunnel(
                name=tunnel_name,
                adapter="wireguard",
                session_name=config.session_name,
                username=config.username,
                device=interface_name,
                namespace=None,  # Could put in namespace if desired
                endpoint=config.endpoint,
                connected_at=asyncio.get_event_loop().time(),
                metadata={"config_path": config_path},
            )

            self._tunnels[tunnel_name] = {
                "interface": interface_name,
                "config_path": config_path,
            }

            return tunnel

        except Exception as e:
            logger.error(f"WireGuard connection failed: {e}")
            raise ConnectionError(f"WireGuard connection failed: {e}") from e

    async def disconnect(self, tunnel: Tunnel):
        """Disconnect WireGuard tunnel."""
        tunnel_name = tunnel.name
        tunnel_info = self._tunnels.get(tunnel_name)

        if tunnel_info:
            interface_name = tunnel_info["interface"]
            try:
                proc = await asyncio.create_subprocess_exec(
                    "wg-quick", "down", interface_name,
                    stdout=asyncio.subprocess.PIPE,
                    stderr=asyncio.subprocess.PIPE,
                )
                await proc.communicate()

                # Clean up config file
                import os
                config_path = tunnel_info.get("config_path")
                if config_path and os.path.exists(config_path):
                    os.remove(config_path)

            except Exception as e:
                logger.warning(f"Error bringing down WireGuard: {e}")
            finally:
                self._tunnels.pop(tunnel_name, None)

    async def get_status(self, tunnel: Tunnel) -> TunnelStatus:
        """Get WireGuard interface status."""
        interface_name = tunnel.device
        try:
            # Check if interface exists via ip link
            proc = await asyncio.create_subprocess_exec(
                "ip", "link", "show", interface_name,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
            )
            stdout, stderr = await proc.communicate()

            if proc.returncode == 0:
                return TunnelStatus.CONNECTED
            else:
                return TunnelStatus.DISCONNECTED
        except Exception:
            return TunnelStatus.ERROR

    async def get_traffic_stats(self, tunnel: Tunnel) -> tuple:
        """Get traffic stats from wg show."""
        interface_name = tunnel.device
        try:
            proc = await asyncio.create_subprocess_exec(
                "wg", "show", interface_name, "transfer",
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
            )
            stdout, stderr = await proc.communicate()

            if proc.returncode == 0:
                lines = stdout.decode().strip().split("\n")
                if len(lines) >= 2:
                    # Parse "transfer" line: peer <public_key> <rx_bytes> <tx_bytes> ...
                    parts = lines[1].split()
                    if len(parts) >= 3:
                        rx_bytes = int(parts[1])
                        tx_bytes = int(parts[2])
                        tunnel.bytes_in = rx_bytes
                        tunnel.bytes_out = tx_bytes
                        return (rx_bytes, tx_bytes)

            return (0, 0)
        except Exception as e:
            logger.error(f"Error getting WireGuard stats: {e}")
            return (0, 0)

    async def list_tunnels(self) -> List[Tunnel]:
        """List all active WireGuard tunnels."""
        tunnels = []
        for tunnel_name, info in self._tunnels.items():
            # We stored minimal info; reconstruct Tunnel object
            tunnel = Tunnel(
                name=tunnel_name,
                adapter="wireguard",
                session_name="",  # not stored; could be from config but not tracked
                username="",
                device=info["interface"],
                namespace=None,
                endpoint=None,
                metadata={"config_path": info["config_path"]},
            )
            tunnels.append(tunnel)
        return tunnels

    async def get_capabilities(self) -> AdapterCapabilities:
        """Return WireGuard adapter capabilities."""
        return self.capabilities

    async def cleanup(self):
        """Clean up all WireGuard tunnels."""
        for tunnel_name, tunnel_info in list(self._tunnels.items()):
            interface_name = tunnel_info["interface"]
            try:
                await asyncio.create_subprocess_exec(
                    "wg-quick", "down", interface_name,
                    stdout=asyncio.subprocess.DEVNULL,
                    stderr=asyncio.subprocess.DEVNULL,
                )
                import os
                config_path = tunnel_info.get("config_path")
                if config_path and os.path.exists(config_path):
                    os.remove(config_path)
            except Exception:
                pass
        self._tunnels.clear()
