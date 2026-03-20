"""WireGuard Adapter for libvpnmanager."""

from .adapter import WireGuardAdapter
from .sessions.wireguard import WireGuardSession

__version__ = "0.1.0.dev0"
__all__ = ["WireGuardAdapter", "WireGuardSession"]
