"""WebSocket IPC transport.

Provides IPC over WebSocket, optionally secure (wss://).
Works on all platforms with Python 3.7+.

Allows local or remote daemon control (if TLS and auth configured).
"""

import asyncio
import json
import ssl
import warnings
from typing import Any, Dict, Callable, Awaitable, Optional
from ..models.exceptions import VPNManagerError

try:
    import websockets
    from websockets.server import WebSocketServerProtocol
    from websockets.client import WebSocketClientProtocol
    WEBSOCKETS_AVAILABLE = True
except ImportError:
    WEBSOCKETS_AVAILABLE = False
    WebSocketServerProtocol = type(None)
    WebSocketClientProtocol = type(None)

from .transport import (
    IPCTransport, IPCServer, IPCClient, Message, MessageType, TransportConfig, IPCError, register_transport,
    create_ssl_context, create_client_ssl_context
)


class WebSocketServer(IPCServer):
    """WebSocket IPC server with SSL/TLS support."""

    DEFAULT_HOST = "127.0.0.1"
    DEFAULT_PORT = 8765

    def __init__(self, manager: Any, config: TransportConfig):
        super().__init__(manager)
        self.config = config
        self.host = config.extra.get('host', self.DEFAULT_HOST)
        self.port = config.extra.get('port', self.DEFAULT_PORT)

        # SSL configuration - either provide an existing SSLContext or build from cert files
        self.ssl: Optional[ssl.SSLContext] = config.extra.get('ssl')
        if self.ssl is None:
            # Build SSL context from certificate configuration if certfile provided
            certfile = config.extra.get('certfile')
            keyfile = config.extra.get('keyfile')
            cafile = config.extra.get('cafile')
            verify_client = config.extra.get('verify_client', False)

            if certfile:
                self.ssl = create_ssl_context(
                    certfile=certfile,
                    keyfile=keyfile,
                    cafile=cafile,
                    verify_mode=ssl.CERT_REQUIRED if verify_client else ssl.CERT_NONE,
                    password=config.extra.get('password')
                )
                self.verify_client = verify_client
            else:
                self.ssl = None
                self.verify_client = False

        self._server: Optional[asyncio.Server] = None
        self._clients: set[WebSocketServerProtocol] = set()

    async def start(self) -> None:
        """Start WebSocket server."""
        if not WEBSOCKETS_AVAILABLE:
            raise IPCError("websockets library not installed. Install with: pip install websockets")

        if self.ssl:
            logger = getattr(self.manager, 'logger', None)
            if logger:
                logger.info(f"WebSocket IPC server starting with SSL/TLS on {self.host}:{self.port}")
                if self.verify_client:
                    logger.info("Client certificate verification enabled (mutual TLS)")
            else:
                print(f"WebSocket IPC server starting with SSL/TLS on {self.host}:{self.port} (mutual TLS: {self.verify_client})")

        self._server = await websockets.serve(
            self._handle_client,
            self.host,
            self.port,
            ssl=self.ssl,
            max_size=10 * 1024 * 1024,  # 10 MB max message
        )
        protocol = "wss" if self.ssl else "ws"
        print(f"WebSocket IPC server listening on {self.host}:{self.port} ({protocol})")

    async def stop(self) -> None:
        """Stop server."""
        if self._server:
            self._server.close()
            await self._server.wait_closed()
            self._server = None

        # Close all clients
        for ws in list(self._clients):
            try:
                await ws.close()
            except:
                pass
        self._clients.clear()

    async def emit_signal(self, signal: str, data: Dict[str, Any]) -> None:
        """Send signal to all connected clients."""
        msg = Message.signal(signal, data)
        payload = self._serialize_message(msg)

        for ws in list(self._clients):
            try:
                await ws.send(payload)
            except Exception:
                self._clients.discard(ws)

    async def _handle_client(self, websocket: WebSocketServerProtocol, path: str) -> None:
        """Handle a client connection."""
        self._clients.add(websocket)
        try:
            async for raw in websocket:
                if not isinstance(raw, bytes):
                    continue
                try:
                    msg = self._deserialize_message(raw)
                    response = await self.handle_request(msg)
                    resp_data = self._serialize_message(response)
                    await websocket.send(resp_data)
                except Exception as e:
                    error_msg = Message.error(0, str(e))
                    await websocket.send(self._serialize_message(error_msg))
        except websockets.exceptions.ConnectionClosed:
            pass
        finally:
            self._clients.discard(websocket)

    def _serialize_message(self, message: Message) -> bytes:
        data = message.to_dict()
        return json.dumps(data).encode('utf-8')

    def _deserialize_message(self, data: bytes) -> Message:
        obj = json.loads(data.decode('utf-8'))
        return Message(
            msg_type=MessageType(obj['type']),
            method=obj.get('method'),
            params=obj.get('params', {}),
            request_id=obj.get('request_id'),
            result=obj.get('result'),
            error=obj.get('error'),
            signal_name=obj.get('signal'),
        )


class WebSocketClient(IPCClient):
    """WebSocket IPC client with SSL/TLS support."""

    def __init__(self, config: TransportConfig):
        super().__init__()
        self.config = config
        self.uri = config.extra.get('uri', 'ws://127.0.0.1:8765')

        # SSL configuration - build SSL context if needed
        self.ssl_context: Optional[ssl.SSLContext] = config.extra.get('ssl')
        if self.ssl_context is None and (config.extra.get('certfile') or config.extra.get('cafile')):
            # Extract server hostname from URI for SNI/verification
            server_hostname = None
            if self.uri.startswith('wss://'):
                # Parse hostname from URI (remove wss:// and any port)
                uri_parts = self.uri[6:].split('/')[0].split(':')
                server_hostname = uri_parts[0] if uri_parts[0] else None

            self.ssl_context = create_client_ssl_context(
                certfile=config.extra.get('certfile'),
                keyfile=config.extra.get('keyfile'),
                cafile=config.extra.get('cafile'),
                verify_mode=ssl.CERT_REQUIRED if config.extra.get('verify', True) else ssl.CERT_NONE,
                password=config.extra.get('password'),
                server_hostname=server_hostname
            )

        self._ws: Optional[WebSocketClientProtocol] = None
        self._pending: Dict[int, asyncio.Future] = {}
        self._request_counter = 0
        self._listen_task: Optional[asyncio.Task] = None

    async def connect(self) -> None:
        """Connect to WebSocket server."""
        if not WEBSOCKETS_AVAILABLE:
            raise IPCError("websockets library not installed")

        connect_kwargs = {}
        if self.ssl_context:
            connect_kwargs['ssl'] = self.ssl_context
            # For wss:// URIs, we may also need to disable hostname check if not verified
            if isinstance(self.ssl_context.verify_mode, ssl.VerifyMode) and self.ssl_context.verify_mode == ssl.CERT_NONE:
                connect_kwargs['server_hostname'] = None  # Disable SNI

        self._ws = await websockets.connect(self.uri, **connect_kwargs)
        self.connected = True
        self._listen_task = asyncio.create_task(self._listen_loop())

    async def disconnect(self) -> None:
        """Disconnect."""
        if self._listen_task:
            self._listen_task.cancel()
            try:
                await self._listen_task
            except asyncio.CancelledError:
                pass
            self._listen_task = None

        if self._ws:
            await self._ws.close()
            self._ws = None
        self.connected = False

        for future in self._pending.values():
            if not future.done():
                future.set_exception(IPCError("Disconnected"))
        self._pending.clear()

    async def call_method(
        self,
        method: str,
        params: Optional[Dict[str, Any]] = None
    ) -> Any:
        """Call a method via WebSocket."""
        if not self.connected or not self._ws:
            raise IPCError("Not connected")

        req_id = self._request_counter
        self._request_counter += 1
        future = asyncio.Future()
        self._pending[req_id] = future

        msg = Message.request(method, params or {}, req_id)
        data = self._serialize_message(msg)
        await self._ws.send(data)

        try:
            response = await asyncio.wait_for(future, timeout=30.0)
            if response.error:
                raise IPCError(response.error)
            return response.result
        except asyncio.TimeoutError:
            self._pending.pop(req_id, None)
            raise IPCError("Request timeout")

    async def subscribe_signal(
        self,
        signal: str,
        callback: Callable[[Dict[str, Any]], Awaitable[None]]
    ) -> None:
        """Subscribe to a signal. Not implemented yet (would need server-side registry)."""
        pass

    async def _listen_loop(self) -> None:
        """Listen for incoming messages (responses and signals)."""
        try:
            async for raw in self._ws:
                if not isinstance(raw, bytes):
                    continue
                msg = self._deserialize_message(raw)
                if msg.msg_type == MessageType.RESPONSE:
                    future = self._pending.get(msg.request_id)
                    if future and not future.done():
                        future.set_result(msg)
                elif msg.msg_type == MessageType.ERROR:
                    future = self._pending.get(msg.request_id)
                    if future and not future.done():
                        future.set_exception(IPCError(msg.error or "Unknown error"))
                elif msg.msg_type == MessageType.SIGNAL:
                    # Signal received - could invoke callbacks
                    pass
        except Exception as e:
            # Connection closed or error
            pass

    def _serialize_message(self, message: Message) -> bytes:
        data = message.to_dict()
        return json.dumps(data).encode('utf-8')

    def _deserialize_message(self, data: bytes) -> Message:
        obj = json.loads(data.decode('utf-8'))
        return Message(
            msg_type=MessageType(obj['type']),
            method=obj.get('method'),
            params=obj.get('params', {}),
            request_id=obj.get('request_id'),
            result=obj.get('result'),
            error=obj.get('error'),
            signal_name=obj.get('signal'),
        )


# Register this transport (must be after class definitions)
register_transport('websocket', WebSocketServer, WebSocketClient)
