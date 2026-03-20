"""Mocks for proton.vpn.core.api and related classes.

These mocks simulate the Proton VPN core API for testing the adapter without
requiring the real proton-vpn-api-core package.

Design:
- ProtonVPNAPI: Factory for connectors; holds client metadata.
- MultiTunnelConnector: Manages multiple concurrent connections by tunnel_name.
- SingleTunnelConnector: Legacy single-connection mode.
- MockVPNConnection: Simulates a VPN connection with async connect, state
  monitoring, traffic stats, and optional state change subscriptions.
"""

import asyncio
import logging
from typing import Dict, List, Optional, Callable, AsyncIterator
from dataclasses import dataclass, field
from enum import Enum

from .connection import ConnectionStateEnum
from .session_holder import ClientTypeMetadata
from ..session.dataclasses.servers import LogicalServer, ServerList


logger = logging.getLogger(__name__)


@dataclass
class _StatusMessage:
    """Internal class representing a status update with a message."""
    message: str
    state: ConnectionStateEnum


class MockVPNConnection:
    """
    Mock VPN connection that simulates a single tunnel connection.

    Provides async connect, state management, traffic stats, and optional
    state change subscriptions.
    """

    def __init__(self, tunnel_name: str, server: LogicalServer, protocol: str):
        self.tunnel_name = tunnel_name
        self.server = server
        self.protocol = protocol
        self._state = ConnectionStateEnum.DISCONNECTED
        self._state_listeners: List[Callable] = []
        self._tun_device = f"proton-{tunnel_name[:8]}"
        self._endpoint = f"{server.server_name}.proton.net"
        self._gateway = "10.7.0.1"
        self._dns_servers = ["1.1.1.1", "1.0.0.1"]
        self._bytes_received = 0
        self._bytes_sent = 0
        self._connect_task: Optional[asyncio.Task] = None
        self._disconnect_event = asyncio.Event()
        self._monitor_queue: Optional[asyncio.Queue] = None
        # Attribute versions for list_tunnels compatibility
        self.device = self._tun_device
        self.endpoint = self._endpoint
        self.id = tunnel_name  # simplify

    def get_tun_device_name(self) -> str:
        return self._tun_device

    def get_endpoint(self) -> str:
        return self._endpoint

    def get_state(self) -> ConnectionStateEnum:
        return self._state

    def get_gateway_ip(self) -> str:
        return self._gateway

    def get_dns_servers(self) -> List[str]:
        return self._dns_servers.copy()

    def get_statistics(self):
        """Return an object with bytes_in and bytes_out attributes."""
        return _Stats(self._bytes_received, self._bytes_sent)

    def get_bytes_received(self) -> int:
        return self._bytes_received

    def get_bytes_sent(self) -> int:
        return self._bytes_sent

    def subscribe(self, callback: Callable):
        if callback not in self._state_listeners:
            self._state_listeners.append(callback)

    def unsubscribe(self, callback: Callable):
        if callback in self._state_listeners:
            self._state_listeners.remove(callback)

    def _set_state(self, new_state: ConnectionStateEnum):
        if self._state != new_state:
            old_state = self._state
            self._state = new_state
            logger.debug(f"Connection '{self.tunnel_name}' state: {old_state} -> {new_state}")
            for cb in self._state_listeners:
                try:
                    cb(new_state, self)
                except Exception as e:
                    logger.warning(f"State listener error: {e}")

    async def _connect_simulation(self):
        """Simulate the async connection process."""
        try:
            self._set_state(ConnectionStateEnum.CONNECTING)
            # Simulate handshake delay
            await asyncio.sleep(0.2)
            self._set_state(ConnectionStateEnum.CONNECTED)
            logger.info(f"Mock connection '{self.tunnel_name}' established")
            # Wait for disconnect signal
            await self._disconnect_event.wait()
        except asyncio.CancelledError:
            logger.debug(f"Connect simulation cancelled for {self.tunnel_name}")
        finally:
            if self._state != ConnectionStateEnum.DISCONNECTED:
                self._set_state(ConnectionStateEnum.DISCONNECTING)
                await asyncio.sleep(0.05)
                self._set_state(ConnectionStateEnum.DISCONNECTED)

    async def connect(self) -> 'MockVPNConnection':
        if self._connect_task and not self._connect_task.done():
            return self
        self._disconnect_event.clear()
        self._connect_task = asyncio.create_task(self._connect_simulation())
        # Wait for CONNECTED state
        try:
            await asyncio.wait_for(self._wait_for_state(ConnectionStateEnum.CONNECTED), timeout=2.0)
        except asyncio.TimeoutError:
            logger.warning(f"Mock connection '{self.tunnel_name}' timed out waiting for CONNECTED")
        return self

    async def _wait_for_state(self, target_state: ConnectionStateEnum):
        while self._state != target_state:
            if self._state == ConnectionStateEnum.ERROR:
                raise ConnectionError(f"Connection entered ERROR state while waiting for {target_state}")
            await asyncio.sleep(0.01)

    def _state_message(self, state: ConnectionStateEnum) -> str:
        """Map state to human-readable message."""
        return {
            ConnectionStateEnum.CONNECTING: "Connecting...",
            ConnectionStateEnum.CONNECTED: "Connected",
            ConnectionStateEnum.DISCONNECTING: "Disconnecting...",
            ConnectionStateEnum.DISCONNECTED: "Disconnected",
            ConnectionStateEnum.ERROR: "Error",
        }.get(state, "Unknown")

    def monitor(self) -> AsyncIterator[_StatusMessage]:
        """
        Async iterator that yields status messages until the connection reaches
        a terminal state (CONNECTED, ERROR, or DISCONNECTED).
        """
        async def _generator():
            # Yield initial state
            state = self.get_state()
            yield _StatusMessage(message=self._state_message(state), state=state)
            # If terminal, stop
            if state in (ConnectionStateEnum.CONNECTED, ConnectionStateEnum.ERROR, ConnectionStateEnum.DISCONNECTED):
                return
            # Wait for state changes and yield updates
            while True:
                await asyncio.sleep(0.05)
                new_state = self.get_state()
                if new_state != state:
                    state = new_state
                    yield _StatusMessage(message=self._state_message(state), state=state)
                    if state in (ConnectionStateEnum.CONNECTED, ConnectionStateEnum.ERROR, ConnectionStateEnum.DISCONNECTED):
                        break
        return _generator()

    async def disconnect(self):
        """Request disconnection."""
        if self._connect_task and not self._connect_task.done():
            self._disconnect_event.set()
            try:
                await asyncio.wait_for(self._connect_task, timeout=2.0)
            except asyncio.CancelledError:
                pass
        self._connect_task = None


class _Stats:
    """Simple stats object with bytes_in and bytes_out."""
    def __init__(self, received: int, sent: int):
        self.bytes_in = received
        self.bytes_out = sent


class MultiTunnelConnector:
    """
    Mock multi-tunnel connector that supports multiple concurrent connections
    by tunnel_name.
    """

    def __init__(self, api: 'MockProtonVPNAPI'):
        self.api = api
        self._connections: Dict[str, MockVPNConnection] = {}
        self._lock = asyncio.Lock()

    async def connect(
        self, tunnel_name: str, server, protocol: str
    ) -> MockVPNConnection:
        """
        Create or reuse a connection for the given tunnel_name.
        """
        async with self._lock:
            if tunnel_name in self._connections:
                existing = self._connections[tunnel_name]
                if existing.get_state() in (ConnectionStateEnum.CONNECTED, ConnectionStateEnum.CONNECTING):
                    logger.info(f"Reusing existing connection for tunnel '{tunnel_name}'")
                    return existing
                else:
                    await existing.disconnect()
                    del self._connections[tunnel_name]

            logger.info(f"Creating new connection for tunnel '{tunnel_name}' to {server.server_name}")
            connection = MockVPNConnection(tunnel_name, server, protocol)
            self._connections[tunnel_name] = connection
            await connection.connect()
            return connection

    def list_tunnels(self) -> List[str]:
        """Return list of active tunnel names."""
        return list(self._connections.keys())

    async def disconnect(self, tunnel_name: str):
        """Disconnect a specific tunnel."""
        async with self._lock:
            conn = self._connections.pop(tunnel_name, None)
            if conn:
                await conn.disconnect()
                logger.info(f"Disconnected tunnel '{tunnel_name}'")

    async def disconnect_all(self):
        """Disconnect all tunnels."""
        async with self._lock:
            for name, conn in list(self._connections.items()):
                try:
                    await conn.disconnect()
                except Exception as e:
                    logger.warning(f"Error disconnecting {name}: {e}")
            self._connections.clear()

    def get_connection(self, tunnel_name: str) -> Optional[MockVPNConnection]:
        """Get connection by tunnel name."""
        return self._connections.get(tunnel_name)

    def get_tunnel_connection(self, tunnel_name: str) -> Optional[MockVPNConnection]:
        """Alias for get_connection."""
        return self.get_connection(tunnel_name)


class SingleTunnelConnector:
    """
    Mock single-tunnel connector (legacy mode). Supports only one connection.
    """

    def __init__(self, api: 'MockProtonVPNAPI'):
        self.api = api
        self._connection: Optional[MockVPNConnection] = None
        self._lock = asyncio.Lock()

    async def connect(self, server, protocol: str) -> MockVPNConnection:
        async with self._lock:
            if self._connection:
                if self._connection.get_state() in (ConnectionStateEnum.CONNECTED, ConnectionStateEnum.CONNECTING):
                    await self._connection.disconnect()
                    self._connection = None

            tunnel_name = server.server_name
            connection = MockVPNConnection(tunnel_name, server, protocol)
            self._connection = connection
            await connection.connect()
            return connection

    async def disconnect(self):
        async with self._lock:
            if self._connection:
                await self._connection.disconnect()
                self._connection = None

    def get_connection(self) -> Optional[MockVPNConnection]:
        return self._connection


class MockProtonVPNAPI:
    """
    Mock implementation of ProtonVPNAPI.
    """

    def __init__(self, metadata: Optional[ClientTypeMetadata] = None):
        self.metadata = metadata
        self._server_list: Optional[ServerList] = None
        self._multi_connector: Optional[MultiTunnelConnector] = None
        self._single_connector: Optional[SingleTunnelConnector] = None
        self._initialize_default_servers()

    def _initialize_default_servers(self):
        servers = [
            LogicalServer(
                server_name="ch-001.proton.net",
                id="CH-Zurich-1",
                country="CH",
                entry_country="DE",
                exit_country="CH",
                load=50,
            ),
            LogicalServer(
                server_name="de-001.proton.net",
                id="DE-Berlin-1",
                country="DE",
                entry_country="NL",
                exit_country="DE",
                load=30,
            ),
            LogicalServer(
                server_name="us-east-001.proton.net",
                id="US-NY-1",
                country="US",
                entry_country="CA",
                exit_country="US",
                load=70,
            ),
            LogicalServer(
                server_name="uk-001.proton.net",
                id="UK-London-1",
                country="GB",
                entry_country="FR",
                exit_country="GB",
                load=45,
            ),
        ]
        self._server_list = ServerList(servers)

    def get_server_list(self) -> ServerList:
        return self._server_list

    def get_multi_tunnel_connector(self) -> MultiTunnelConnector:
        if self._multi_connector is None:
            self._multi_connector = MultiTunnelConnector(self)
        return self._multi_connector

    def get_vpn_connector(self) -> SingleTunnelConnector:
        if self._single_connector is None:
            self._single_connector = SingleTunnelConnector(self)
        return self._single_connector

    async def logout(self):
        """Cleanup on logout."""
        if self._multi_connector:
            await self._multi_connector.disconnect_all()
        if self._single_connector:
            try:
                await self._single_connector.disconnect()
            except Exception:
                pass
        self._multi_connector = None
        self._single_connector = None
