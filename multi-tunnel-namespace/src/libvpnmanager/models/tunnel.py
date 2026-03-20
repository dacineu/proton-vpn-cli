"""Tunnel data model."""

from dataclasses import dataclass, field
from datetime import datetime
from typing import Dict, Any, Optional, List

from .status import TunnelStatus


@dataclass
class Tunnel:
    """
    Represents a VPN tunnel instance.

    Attributes:
        name: Unique tunnel identifier (user-provided)
        adapter: Adapter type ("proton", "psiphon", etc.)
        device: TUN device name (e.g., "tun0", "proton0")
        namespace: Network namespace name for isolation (None if not isolated)
        endpoint: VPN server/exit node identifier (hostname or IP)
        connected_at: When the tunnel was established
        bytes_in: Total bytes received through tunnel
        bytes_out: Total bytes sent through tunnel
        metadata: Adapter-specific additional data (server config, protocol, etc.)
        session_name: Session identifier (for multi-session adapters)
        username: OS username who owns this tunnel
        status: Connection status (computed from device if not provided)
        gateway: VPN gateway IP address (assigned by server)
        dns_servers: List of DNS server IPs provided by VPN
        vpn_ip: Client IP address assigned by VPN (the IP on the TUN device)
    """

    name: str
    adapter: str
    device: str
    namespace: Optional[str] = None
    endpoint: Optional[str] = None
    connected_at: Optional[datetime] = None
    bytes_in: int = 0
    bytes_out: int = 0
    metadata: Dict[str, Any] = field(default_factory=dict)
    session_name: Optional[str] = None
    username: Optional[str] = None
    gateway: Optional[str] = None
    dns_servers: Optional[List[str]] = None
    vpn_ip: Optional[str] = None

    def to_dict(self) -> Dict[str, Any]:
        """Convert tunnel to dictionary for D-Bus serialization."""
        result = {
            "name": self.name,
            "adapter": self.adapter,
            "device": self.device,
            "namespace": self.namespace,
            "endpoint": self.endpoint,
            "bytes_in": self.bytes_in,
            "bytes_out": self.bytes_out,
            "session_name": self.session_name,
            "username": self.username,
        }
        if self.connected_at:
            result["connected_at"] = self.connected_at.isoformat()
        if self.metadata:
            result["metadata"] = self.metadata
        if self.gateway:
            result["gateway"] = self.gateway
        if self.dns_servers:
            result["dns_servers"] = self.dns_servers
        if self.vpn_ip:
            result["vpn_ip"] = self.vpn_ip
        return result

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "Tunnel":
        """Create tunnel from dictionary (e.g., D-Bus response)."""
        connected_at = None
        if "connected_at" in data and data["connected_at"]:
            try:
                connected_at = datetime.fromisoformat(data["connected_at"])
            except (ValueError, TypeError):
                connected_at = None

        # Note: 'status' is computed, not stored; ignore if present
        return cls(
            name=data["name"],
            adapter=data["adapter"],
            device=data["device"],
            namespace=data.get("namespace"),
            endpoint=data.get("endpoint"),
            connected_at=connected_at,
            bytes_in=data.get("bytes_in", 0),
            bytes_out=data.get("bytes_out", 0),
            metadata=data.get("metadata", {}),
            session_name=data.get("session_name"),
            username=data.get("username"),
            gateway=data.get("gateway"),
            dns_servers=data.get("dns_servers"),
            vpn_ip=data.get("vpn_ip"),
        )

    @property
    def status(self) -> TunnelStatus:
        """Compute tunnel status based on device presence."""
        return TunnelStatus.CONNECTED if self.device else TunnelStatus.DISCONNECTED
