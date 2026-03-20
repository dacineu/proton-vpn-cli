"""Multi-tunnel VPN manager library.

This library provides:
- TunnelManager: orchestrates VPN adapters and routing strategies
- NetworkNamespaceRouting: complete isolation via network namespaces (Option 1)
- VPNAdapter ABC: base class for VPN backends (Proton, Psiphon, etc.)
- Data models: Tunnel, ConnectionConfig, TunnelStatus
- D-Bus service for remote control
"""

from .manager import TunnelManager
from .routing import RoutingStrategy, NetworkNamespaceRouting
from .adapters.base import VPNAdapter, AdapterCapabilities
from .adapters.dummy import DummyAdapter
from .adapters.proton import ProtonVPNAdapter
from .models import (
    Tunnel,
    ConnectionConfig,
    ProtonConnectionConfig,
    PsiphonConnectionConfig,
    WireGuardConnectionConfig,
    TunnelStatus,
)
from .models.exceptions import (
    VPNManagerError,
    TunnelError,
    TunnelNotFoundError,
    TunnelExistsError,
    AdapterError,
    AdapterNotFoundError,
    ConnectionError,
    AuthenticationError,
    ConfigurationError,
    RoutingError,
    NamespaceError,
    NamespaceExistsError,
    NamespaceNotFoundError,
    NamespacePermissionError,
    DeviceError,
    DeviceNotFoundError,
    DeviceExistsError,
    DBusError,
    CapabilityError,
)

__version__ = "0.1.0.dev0"

__all__ = [
    # Core
    "TunnelManager",
    "RoutingStrategy",
    "NetworkNamespaceRouting",
    "VPNAdapter",
    "DummyAdapter",
    "ProtonVPNAdapter",
    "AdapterCapabilities",
    # Models
    "Tunnel",
    "ConnectionConfig",
    "ProtonConnectionConfig",
    "PsiphonConnectionConfig",
    "WireGuardConnectionConfig",
    "TunnelStatus",
    # Exceptions
    "VPNManagerError",
    "TunnelError",
    "TunnelNotFoundError",
    "TunnelExistsError",
    "AdapterError",
    "AdapterNotFoundError",
    "ConnectionError",
    "AuthenticationError",
    "ConfigurationError",
    "RoutingError",
    "NamespaceError",
    "NamespaceExistsError",
    "NamespaceNotFoundError",
    "NamespacePermissionError",
    "DeviceError",
    "DeviceNotFoundError",
    "DeviceExistsError",
    "DBusError",
    "CapabilityError",
]
