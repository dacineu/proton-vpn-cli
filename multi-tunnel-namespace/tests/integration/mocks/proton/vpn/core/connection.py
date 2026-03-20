"""Mock implementation of proton.vpn.core.connection.ConnectionStateEnum."""

from enum import Enum


class ConnectionStateEnum(Enum):
    DISCONNECTED = "DISCONNECTED"
    CONNECTING = "CONNECTING"
    CONNECTED = "CONNECTED"
    DISCONNECTING = "DISCONNECTING"
    ERROR = "ERROR"
