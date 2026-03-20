"""Tunnel status enumeration."""

from enum import Enum


class TunnelStatus(str, Enum):
    """Tunnel connection state."""

    DISCONNECTED = "disconnected"
    CONNECTING = "connecting"
    CONNECTED = "connected"
    DISCONNECTING = "disconnecting"
    ERROR = "error"

    def __str__(self) -> str:
        return self.value
