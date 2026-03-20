"""Data models for libvpnmanager."""

from .status import TunnelStatus
from .tunnel import Tunnel
from .config import (
    ConnectionConfig,
    ProtonConnectionConfig,
    PsiphonConnectionConfig,
    WireGuardConnectionConfig,
)
from .exceptions import (
    VPNManagerError,
    TunnelError,
    TunnelNotFoundError,
    TunnelExistsError,
    AdapterError,
    RoutingError,
    NamespaceError,
    DeviceError,
    DBusError,
    SessionError,
)

__all__ = [
    "TunnelStatus",
    "Tunnel",
    "ConnectionConfig",
    "ProtonConnectionConfig",
    "PsiphonConnectionConfig",
    "WireGuardConnectionConfig",
    "VPNManagerError",
    "TunnelError",
    "TunnelNotFoundError",
    "TunnelExistsError",
    "AdapterError",
    "RoutingError",
    "NamespaceError",
    "DeviceError",
    "DBusError",
    "SessionError",
]
