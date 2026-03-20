"""Custom exceptions for libvpnmanager."""


class VPNManagerError(Exception):
    """Base exception for all libvpnmanager errors."""

    pass


class TunnelError(VPNManagerError):
    """Base tunnel-related error."""

    pass


class TunnelNotFoundError(TunnelError):
    """Requested tunnel does not exist."""

    pass


class TunnelExistsError(TunnelError):
    """Tunnel with given name already exists."""

    pass


class AdapterError(VPNManagerError):
    """VPN adapter error."""

    pass


class AdapterNotFoundError(AdapterError):
    """Requested adapter not found or not registered."""

    pass


class ConnectionError(AdapterError):
    """Failed to establish VPN connection."""

    pass


class AuthenticationError(ConnectionError):
    """Authentication failed (bad credentials)."""

    pass


class ConfigurationError(AdapterError):
    """Invalid configuration provided."""

    pass


class RoutingError(VPNManagerError):
    """Routing strategy error."""

    pass


class NamespaceError(RoutingError):
    """Network namespace error."""

    pass


class NamespaceExistsError(NamespaceError):
    """Namespace already exists."""

    pass


class NamespaceNotFoundError(NamespaceError):
    """Namespace does not exist."""

    pass


class NamespacePermissionError(NamespaceError):
    """Insufficient permissions for namespace operation."""

    pass


class DeviceError(RoutingError):
    """TUN/TAP device error."""

    pass


class DeviceNotFoundError(DeviceError):
    """Requested device does not exist."""

    pass


class DeviceExistsError(DeviceError):
    """Device already exists."""

    pass


class DBusError(VPNManagerError):
    """D-Bus communication error."""

    pass


class CapabilityError(AdapterError):
    """Operation not supported by adapter capabilities."""

    pass


class AccessDeniedError(VPNManagerError):
    """Permission denied (ownership or admin rights required)."""

    pass


class SessionError(VPNManagerError):
    """Session-related errors (login, logout, session management)."""

    pass


class SessionNotFoundError(SessionError):
    """Requested session does not exist."""

    pass
