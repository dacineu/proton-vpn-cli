"""Proton VPN Adapter for libvpnmanager."""

from .adapter import ProtonVPNAdapter
from .sessions.proton import ProtonSession

__version__ = "0.1.0.dev0"
__all__ = ["ProtonVPNAdapter", "ProtonSession"]
