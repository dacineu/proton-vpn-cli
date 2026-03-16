"""Connection configuration models."""

from dataclasses import dataclass, field
from typing import Dict, Any, Optional


@dataclass(kw_only=True)
class ConnectionConfig:
    """
    Base configuration for creating a VPN tunnel.

    Attributes:
        adapter: VPN adapter type ("proton", "psiphon", "wireguard", etc.)
        tunnel_name: Unique identifier for this tunnel
        session_name: Session identifier (for multi-session backends)
    """

    adapter: str
    tunnel_name: str
    session_name: Optional[str] = None

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for serialization."""
        result = {
            "adapter": self.adapter,
            "tunnel_name": self.tunnel_name,
            "session_name": self.session_name,
        }
        return {k: v for k, v in result.items() if v is not None}

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "ConnectionConfig":
        """Create config from dictionary."""
        adapter = data.get("adapter")
        tunnel_name = data.get("tunnel_name")
        session_name = data.get("session_name")
        if not adapter or not tunnel_name:
            raise ValueError("adapter and tunnel_name are required")

        config_type = data.get("config_type")
        if config_type is None:
            # Infer from adapter if config_type not provided
            if adapter == "proton":
                config_type = "proton"
            elif adapter == "psiphon":
                config_type = "psiphon"
            elif adapter == "wireguard":
                config_type = "wireguard"
        if config_type == "proton":
            return ProtonConnectionConfig.from_dict(data)
        elif config_type == "psiphon":
            return PsiphonConnectionConfig.from_dict(data)
        elif config_type == "wireguard":
            return WireGuardConnectionConfig.from_dict(data)
        else:
            return cls(adapter=adapter, tunnel_name=tunnel_name, session_name=session_name)


@dataclass(kw_only=True)
class ProtonConnectionConfig(ConnectionConfig):
    """
    Proton VPN specific configuration.

    Attributes:
        server_id: Proton server logical ID (e.g., "p1-ams-1")
        country: Country code (e.g., "US", "JP", "DE")
        city: Optional city name
        protocol: VPN protocol ("wireguard", "openvpn-udp", "openvpn-tcp")
        features: Feature flags (safe_mode, nat_type, etc.)
    """

    adapter: str = "proton"  # override with default
    server_id: Optional[str] = None
    country: Optional[str] = None
    city: Optional[str] = None
    protocol: str = "wireguard"
    features: Dict[str, bool] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary."""
        data = super().to_dict()
        data.update({
            "config_type": "proton",
            "server_id": self.server_id,
            "country": self.country,
            "city": self.city,
            "protocol": self.protocol,
            "features": self.features,
        })
        return data

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "ProtonConnectionConfig":
        """Create from dictionary."""
        return cls(
            adapter=data["adapter"],
            tunnel_name=data["tunnel_name"],
            session_name=data.get("session_name"),
            server_id=data.get("server_id"),
            country=data.get("country"),
            city=data.get("city"),
            protocol=data.get("protocol", "wireguard"),
            features=data.get("features", {}),
        )


@dataclass(kw_only=True)
class PsiphonConnectionConfig(ConnectionConfig):
    """
    Psiphon configuration.

    Attributes:
        entry_country: Entry server country code
        exit_country: Desired exit country code (or None for any)
        transport_protocol: "tcp" or "udp"
    """

    adapter: str = "psiphon"  # override with default
    entry_country: Optional[str] = None
    exit_country: Optional[str] = None
    transport_protocol: str = "tcp"

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary."""
        data = super().to_dict()
        data.update({
            "config_type": "psiphon",
            "entry_country": self.entry_country,
            "exit_country": self.exit_country,
            "transport_protocol": self.transport_protocol,
        })
        return data

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "PsiphonConnectionConfig":
        """Create from dictionary."""
        return cls(
            adapter=data["adapter"],
            tunnel_name=data["tunnel_name"],
            session_name=data.get("session_name"),
            entry_country=data.get("entry_country"),
            exit_country=data.get("exit_country"),
            transport_protocol=data.get("transport_protocol", "tcp"),
        )


@dataclass(kw_only=True)
class WireGuardConnectionConfig(ConnectionConfig):
    """
    Native WireGuard configuration (for manual wg-quick style configs).

    Attributes:
        config_file: Path to WireGuard config file
        interface_name: TUN device name (if not using auto)
    """

    adapter: str = "wireguard"  # override with default
    config_file: str
    interface_name: Optional[str] = None

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary."""
        data = super().to_dict()
        data.update({
            "config_type": "wireguard",
            "config_file": self.config_file,
            "interface_name": self.interface_name,
        })
        return data

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "WireGuardConnectionConfig":
        """Create from dictionary."""
        return cls(
            adapter=data["adapter"],
            tunnel_name=data["tunnel_name"],
            session_name=data.get("session_name"),
            config_file=data["config_file"],
            interface_name=data.get("interface_name"),
        )
