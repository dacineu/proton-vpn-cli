"""VPN Adapters for different backends."""

from .base import VPNAdapter, AdapterCapabilities
from .dummy import DummyAdapter
from .proton import ProtonVPNAdapter

__all__ = [
    "VPNAdapter",
    "AdapterCapabilities",
    "DummyAdapter",
    "ProtonVPNAdapter",
]
