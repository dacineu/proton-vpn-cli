"""IPC transport abstraction.

Defines the interface that all IPC transports must implement.
"""

import ssl
import warnings
from abc import ABC, abstractmethod
from enum import Enum
from typing import Any, Dict, Optional, Callable, Awaitable


class MessageType(Enum):
    """IPC message types."""
    REQUEST = "request"   # Client -> Server: method call
    RESPONSE = "response" # Server -> Client: result or error
    SIGNAL = "signal"     # Server -> Client: event notification
    ERROR = "error"       # Either direction: protocol error


class Message:
    """An IPC message."""

    def __init__(
        self,
        msg_type: MessageType,
        method: Optional[str] = None,
        params: Optional[Dict[str, Any]] = None,
        request_id: Optional[int] = None,
        result: Optional[Any] = None,
        error: Optional[str] = None,
        signal_name: Optional[str] = None,
    ):
        self.msg_type = msg_type
        self.method = method
        self.params = params or {}
        self.request_id = request_id
        self.result = result
        self.error = error
        self.signal_name = signal_name

    def to_dict(self) -> Dict[str, Any]:
        d = {"type": self.msg_type.value}
        if self.method:
            d["method"] = self.method
        if self.params:
            d["params"] = self.params
        if self.request_id is not None:
            d["request_id"] = self.request_id
        if self.result is not None:
            d["result"] = self.result
        if self.error:
            d["error"] = self.error
        if self.signal_name:
            d["signal"] = self.signal_name
        return d

    @classmethod
    def request(cls, method: str, params: Dict[str, Any], request_id: int) -> "Message":
        return cls(
            msg_type=MessageType.REQUEST,
            method=method,
            params=params,
            request_id=request_id,
        )

    @classmethod
    def response(cls, request_id: int, result: Any = None, error: Optional[str] = None) -> "Message":
        return cls(
            msg_type=MessageType.RESPONSE,
            request_id=request_id,
            result=result,
            error=error,
        )

    @classmethod
    def signal(cls, signal_name: str, params: Dict[str, Any]) -> "Message":
        return cls(
            msg_type=MessageType.SIGNAL,
            signal_name=signal_name,
            params=params,
        )


class TransportConfig:
    """Configuration for an IPC transport."""

    def __init__(
        self,
        transport_type: str,
        **kwargs
    ):
        self.transport_type = transport_type
        self.extra = kwargs


class IPCError(Exception):
    """Base IPC error."""
    pass


class IPCTransport(ABC):
    """Marker base class for all IPC transport implementations.

    Both IPCServer and IPCClient inherit from this class to provide
    a common type for transport-agnostic code.
    """
    pass


class IPCServer(IPCTransport, ABC):
    """Abstract IPC server.

    The server runs in the daemon process and handles client requests
    by calling methods on a manager object.
    """

    def __init__(self, manager: Any):
        """
        Initialize server.

        Args:
            manager: TunnelManager instance (or any object exposing methods)
        """
        super().__init__()
        self.manager = manager
        self._running = False

    @abstractmethod
    async def start(self) -> None:
        """Start the server and begin listening for connections."""
        pass

    @abstractmethod
    async def stop(self) -> None:
        """Stop the server and cleanup resources."""
        pass

    @abstractmethod
    async def emit_signal(self, signal: str, data: Dict[str, Any]) -> None:
        """Emit a signal to all connected clients."""
        pass

    async def handle_request(self, message: Message) -> Message:
        """
        Handle an incoming request from a client.

        Default implementation calls the manager method.
        Override for custom dispatch logic.
        """
        if message.msg_type != MessageType.REQUEST:
            raise IPCError(f"Expected REQUEST, got {message.msg_type}")

        try:
            # Get method on manager
            if not hasattr(self.manager, message.method):
                raise AttributeError(f"Method {message.method} not found")
            method = getattr(self.manager, message.method)

            # Call it (should be async)
            if not callable(method):
                raise IPCError(f"{message.method} is not callable")
            result = await method(**message.params)

            return Message.response(message.request_id, result=result)
        except Exception as e:
            return Message.response(message.request_id, error=str(e))


class IPCClient(IPCTransport, ABC):
    """Abstract IPC client.

    The client is used by CLI tools or GUI apps to communicate with the daemon.
    """

    def __init__(self):
        super().__init__()
        self.connected = False

    @abstractmethod
    async def connect(self) -> None:
        """Connect to the server."""
        pass

    @abstractmethod
    async def disconnect(self) -> None:
        """Disconnect from the server."""
        pass

    @abstractmethod
    async def call_method(
        self,
        method: str,
        params: Optional[Dict[str, Any]] = None
    ) -> Any:
        """Call a method on the server and return the result."""
        pass

    @abstractmethod
    async def subscribe_signal(
        self,
        signal: str,
        callback: Callable[[Dict[str, Any]], Awaitable[None]]
    ) -> None:
        """Subscribe to a signal."""
        pass


# Global registry for transports
_transport_registry: Dict[str, tuple[type, type]] = {}


def register_transport(name: str, server_cls: type, client_cls: type) -> None:
    """Register a transport implementation."""
    _transport_registry[name] = (server_cls, client_cls)


def list_transports() -> list[str]:
    """List available transport names."""
    return list(_transport_registry.keys())


def get_server_transport(transport_type: str, manager: Any, config: TransportConfig) -> IPCServer:
    """Factory to create an IPC server."""
    if transport_type not in _transport_registry:
        raise ValueError(f"Unknown IPC transport: {transport_type}. Available: {list(_transport_registry.keys())}")
    server_cls, _ = _transport_registry[transport_type]
    return server_cls(manager, config)


def get_client_transport(transport_type: str, config: TransportConfig) -> IPCClient:
    """Factory to create an IPC client."""
    if transport_type not in _transport_registry:
        raise ValueError(f"Unknown IPC transport: {transport_type}. Available: {list(_transport_registry.keys())}")
    _, client_cls = _transport_registry[transport_type]
    return client_cls(config)


# SSL/TLS Utility Functions

def create_ssl_context(
    certfile: Optional[str] = None,
    keyfile: Optional[str] = None,
    cafile: Optional[str] = None,
    verify_mode: ssl.VerifyMode = ssl.CERT_NONE,
    password: Optional[str] = None
) -> ssl.SSLContext:
    """
    Create an SSL context for server-side secure connections.

    Args:
        certfile: Path to server certificate (PEM format)
        keyfile: Path to private key (PEM format). If None, key is read from certfile
        cafile: Path to CA bundle for client verification. If None, uses system defaults
        verify_mode: SSL verification mode for client certificates (CERT_NONE, CERT_OPTIONAL, CERT_REQUIRED)
        password: Password for encrypted private key

    Returns:
        Configured SSLContext for use in servers
    """
    # Always use TLS server protocol
    context = ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER)

    # Set secure options
    context.minimum_version = ssl.TLSVersion.TLSv1_2
    context.set_ciphers('ECDHE+AESGCM:ECDHE+CHACHA20:DHE+AESGCM:DHE+CHACHA20:!aNULL:!eNULL:!EXPORT:!DES:!RC4:!3DES:!MD5:!PSK')

    # Configure client certificate verification (for mutual TLS)
    if verify_mode in (ssl.CERT_REQUIRED, ssl.CERT_OPTIONAL):
        context.verify_mode = verify_mode
        if cafile:
            context.load_verify_locations(cafile)
    else:
        context.verify_mode = ssl.CERT_NONE

    # Load server certificate
    if certfile:
        if keyfile:
            context.load_cert_chain(certfile, keyfile, password)
        else:
            context.load_cert_chain(certfile, password=password)

    return context

    if verify_mode == ssl.CERT_REQUIRED:
        context.verify_mode = ssl.CERT_REQUIRED
        if cafile:
            context.load_verify_locations(cafile)
        # If no cafile, will use system default CA store
    elif verify_mode == ssl.CERT_OPTIONAL:
        context.verify_mode = ssl.CERT_OPTIONAL
        if cafile:
            context.load_verify_locations(cafile)
    else:  # CERT_NONE
        context.verify_mode = ssl.CERT_NONE
        warnings.warn("SSL certificate verification disabled - connection vulnerable to MITM attacks", SecurityWarning)

    # Load server/client certificate if provided
    if certfile:
        if keyfile:
            context.load_cert_chain(certfile, keyfile, password)
        else:
            context.load_cert_chain(certfile, password=password)

    return context


def create_client_ssl_context(
    certfile: Optional[str] = None,
    keyfile: Optional[str] = None,
    cafile: Optional[str] = None,
    verify_mode: ssl.VerifyMode = ssl.CERT_REQUIRED,
    password: Optional[str] = None,
    server_hostname: Optional[str] = None
) -> ssl.SSLContext:
    """
    Create an SSL context specifically for WebSocket clients.

    Args:
        certfile: Client certificate for mutual TLS
        keyfile: Client private key
        cafile: CA bundle to verify server certificate
        verify_mode: Usually CERT_REQUIRED for production
        password: Password for encrypted private key
        server_hostname: Expected server hostname for SNI and verification (optional)

    Returns:
        Configured SSLContext for client connections
    """
    context = ssl.SSLContext(ssl.PROTOCOL_TLS_CLIENT)

    # Minimum TLS 1.2
    context.minimum_version = ssl.TLSVersion.TLSv1_2
    context.set_ciphers('ECDHE+AESGCM:ECDHE+CHACHA20:DHE+AESGCM:DHE+CHACHA20:!aNULL:!eNULL:!EXPORT:!DES:!RC4:!3DES:!MD5:!PSK')

    if verify_mode == ssl.CERT_REQUIRED:
        context.verify_mode = ssl.CERT_REQUIRED
        if cafile:
            context.load_verify_locations(cafile)
        # check_hostname should be True when verify_mode is CERT_REQUIRED
        context.check_hostname = bool(server_hostname)
    else:
        context.verify_mode = verify_mode
        context.check_hostname = False

    # Load client certificate if provided (for mutual TLS)
    if certfile:
        if keyfile:
            context.load_cert_chain(certfile, keyfile, password)
        else:
            context.load_cert_chain(certfile, password=password)

    return context
