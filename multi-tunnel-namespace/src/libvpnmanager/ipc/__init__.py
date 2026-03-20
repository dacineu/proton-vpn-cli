"""Platform-independent IPC layer for libvpnmanager.

This package provides transport abstractions for daemon <-> client communication.
Supported transports:
  - D-Bus (Linux/Unix, system bus)
  - Unix socket (cross-platform, local only)
  - WebSocket (cross-platform, local or remote, secure)
  - Named pipes (Windows)

The daemon can listen on one or more transports simultaneously.
Clients connect using their preferred transport.
"""

from .transport import (
    IPCTransport,
    IPCError,
    IPCServer,
    IPCClient,
    Message,
    MessageType,
    TransportConfig,
    get_server_transport,
    get_client_transport,
    register_transport,
    list_transports,
)

# Automatically import transport implementations to trigger registration
# These imports are safe even if optional dependencies are missing; transports handle that internally.
from . import unix_socket  # noqa: F401
from . import dbus  # noqa: F401
from . import websocket  # noqa: F401

__all__ = [
    "IPCTransport",
    "IPCError",
    "IPCServer",
    "IPCClient",
    "Message",
    "MessageType",
    "TransportConfig",
    "get_server_transport",
    "get_client_transport",
    "register_transport",
    "list_transports",
]
