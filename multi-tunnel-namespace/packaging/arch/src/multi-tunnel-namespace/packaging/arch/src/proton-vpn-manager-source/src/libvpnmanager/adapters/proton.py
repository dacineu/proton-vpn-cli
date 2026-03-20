"""Proton VPN adapter for libvpnmanager.

This adapter integrates with proton-vpn-api-core to create real VPN tunnels.

IMPORTANT: Requires modifications to proton-vpn-api-core to support multi-tunnel:
  - MultiTunnelVPNConnector that accepts tunnel_name and custom TUN name
  - Ability to query active connections by tunnel name
  - get_tun_device_name() method on VPNConnection
  - Ability to have multiple concurrent connections

See docs/ADAPTER_INTEGRATION.md for detailed design.
"""

import asyncio
import logging
from datetime import datetime
from typing import Dict, List, Tuple, Optional

from ..models.tunnel import Tunnel
from ..models.status import TunnelStatus
from ..models.config import ProtonConnectionConfig
from ..models.exceptions import (
    ConnectionError,
    AuthenticationError,
    ConfigurationError,
    TunnelNotFoundError,
    CapabilityError,
    AdapterError,
)

from .base import VPNAdapter, AdapterCapabilities

# These imports will be available when proton-vpn-api-core is installed
try:
    from proton.vpn.core.api import ProtonVPNAPI
    from proton.vpn.core.connection import VPNConnector, VPNConnection, ConnectionStateEnum
    from proton.vpn.core.session_holder import ClientTypeMetadata
    from proton.vpn.session.dataclasses.servers import LogicalServer
    IMPORTS_AVAILABLE = True
except ImportError:
    IMPORTS_AVAILABLE = False
    # Define placeholder types for documentation/type-checking
    ProtonVPNAPI = type(None)
    VPNConnector = type(None)
    VPNConnection = type(None)
    ConnectionStateEnum = type(None)
    LogicalServer = type(None)

logger = logging.getLogger(__name__)


class ProtonVPNAdapter(VPNAdapter):
    """
    Proton VPN adapter implementation.

    This adapter connects to the Proton VPN daemon via proton-vpn-api-core.

    Daemon Requirements:
      - proton-vpn-api-core >= X.Y.Z with multi-tunnel support
      - proton-vpn-local-agent running with appropriate capabilities
      - Session must be authenticated (or we handle login)

    Limitations:
      - Currently proton-vpn-api-core does NOT support multiple concurrent connectors.
        This adapter will need a forked/patched version of the core that provides:
        * MultiTunnelVPNConnector.connect(tunnel_name, server, protocol) -> connection
        * get_connection(tunnel_name) -> Optional[VPNConnection]
        * list_tunnels() -> List[str]
    """

    def __init__(self, manager=None):
        """
        Initialize adapter.

        Args:
            manager: TunnelManager instance (optional, for callback)
        """
        if not IMPORTS_AVAILABLE:
            raise ImportError(
                "proton-vpn-api-core is not installed. "
                "This adapter requires the proton.vpn.core package."
            )

        self.manager = manager
        self.api: Optional[ProtonVPNAPI] = None
        self.connector: Optional[VPNConnector] = None
        self._is_multi_tunnel: bool = False  # Will be set when connector is obtained
        self._local_tunnels: Dict[str, Tunnel] = {}
        self._connections: Dict[str, VPNConnection] = {}
        self._subscribers: Dict[str, callable] = {}

    def register_status_callback(self, tunnel_name: str, callback: callable):
        """Register a callback for status changes on a specific tunnel."""
        if tunnel_name not in self._status_callbacks:
            self._status_callbacks[tunnel_name] = []
        if callback not in self._status_callbacks[tunnel_name]:
            self._status_callbacks[tunnel_name].append(callback)
            logger.debug(f"Registered status callback for tunnel '{tunnel_name}'")

    async def _ensure_api(self):
        """Initialize ProtonVPNAPI if not already."""
        if self.api is None:
            # The API requires ClientTypeMetadata
            metadata = ClientTypeMetadata(
                type="linux-cli",
                version="0.1.8"  # TODO: Get from package version
            )
            self.api = ProtonVPNAPI(metadata)

    async def _ensure_connector(self):
        """Get or create multi-tunnel connector."""
        await self._ensure_api()
        if self.connector is None:
            # Try to get multi-tunnel connector (requires patched daemon)
            # The daemon should expose get_multitunnel_connector() method
            if hasattr(self.api, 'get_multitunnel_connector'):
                try:
                    self.connector = await self.api.get_multitunnel_connector()
                    self._is_multi_tunnel = True
                    logger.info("Using MultiTunnelVPNConnector")
                except Exception as e:
                    logger.warning(f"Failed to get MultiTunnelVPNConnector: {e}. Falling back to single-tunnel connector.")
                    self.connector = await self.api.get_vpn_connector()
                    self._is_multi_tunnel = False
            else:
                # Fall back to standard single-tunnel connector
                logger.warning("MultiTunnelVPNConnector not available in proton-vpn-api-core. Using single-tunnel connector (limited to 1 concurrent connection).")
                self.connector = await self.api.get_vpn_connector()
                self._is_multi_tunnel = False

    async def _wait_for_state(
        self,
        connection: VPNConnection,
        target_state: ConnectionStateEnum,
        timeout: float = 30.0,
        poll_interval: float = 0.1
    ) -> bool:
        """
        Wait for connection to reach target state.

        Args:
            connection: VPNConnection to monitor
            target_state: Desired ConnectionStateEnum
            timeout: Maximum seconds to wait
            poll_interval: How often to check state

        Returns:
            True if reached target state

        Raises:
            asyncio.TimeoutError: If timeout expires
        """
        start_time = asyncio.get_event_loop().time()
        while True:
            current_state = connection.get_connection_state()
            if current_state == target_state:
                return True
            if current_state == ConnectionStateEnum.ERROR:
                raise ConnectionError(f"Connection entered ERROR state while waiting for {target_state}")
            if asyncio.get_event_loop().time() - start_time > timeout:
                raise asyncio.TimeoutError()
            await asyncio.sleep(poll_interval)

    async def _find_server(
        self, config: ProtonConnectionConfig
    ) -> LogicalServer:
        """
        Find a server based on configuration.

        Args:
            config: ProtonConnectionConfig with country/city/server_id

        Returns:
            LogicalServer object

        Raises:
            ConfigurationError: If no server matches
        """
        await self._ensure_api()

        # Get server list from API
        server_list = await self.api.get_server_list()

        # Filter by country if specified
        if config.country:
            servers = server_list.filter_by_country(config.country.upper())
            if not servers:
                raise ConfigurationError(f"No servers available in {config.country}")
            # TODO: Also filter by city, features, etc.
            # For now, just pick first
            return servers[0]

        # If server_id specified, find by ID
        if config.server_id:
            server = server_list.get_by_id(config.server_id)
            if server:
                return server
            raise ConfigurationError(f"Server {config.server_id} not found")

        raise ConfigurationError("Must specify country or server_id")

    async def connect(
        self,
        config: ProtonConnectionConfig,
        progress_callback: Optional[callable] = None,
    ) -> Tunnel:
        """
        Establish a Proton VPN connection.

        Args:
            config: Proton connection configuration
            progress_callback: Optional callable(status: str)

        Returns:
            Tunnel object with populated fields

        Raises:
            ConfigurationError: If server not found or config invalid
            AuthenticationError: If not logged in
            ConnectionError: If connection fails
            CapabilityError: If multi-tunnel not supported by daemon
        """
        if progress_callback:
            progress_callback("connecting")

        await self._ensure_connector()

        # 1. Find target server
        try:
            server = await self._find_server(config)
        except Exception as e:
            raise ConfigurationError(f"Failed to find server: {e}") from e

        # 2. Connect using connector
        # Determine if we have multi-tunnel or single-tunnel connector
        is_multi_tunnel = hasattr(self.connector, 'connect') and 'tunnel_name' in str(
            getattr(self.connector.connect, '__annotations__', {})
        ) or hasattr(self.connector, 'list_tunnels')

        if is_multi_tunnel:
            # Multi-tunnel mode: pass tunnel_name
            try:
                connection = await self.connector.connect(
                    tunnel_name=config.tunnel_name,
                    server=server,
                    protocol=config.protocol
                )
                logger.info(f"Multi-tunnel connection established for '{config.tunnel_name}'")
            except Exception as e:
                raise ConnectionError(f"Failed to establish multi-tunnel connection: {e}") from e
        else:
            # Single-tunnel mode: connect without tunnel_name
            # WARNING: This will disconnect any existing connection
            logger.warning("Using single-tunnel connector. Only one connection can be active at a time.")
            try:
                connection = await self.connector.connect(server, protocol=config.protocol)
                logger.info("Single-tunnel connection established")
            except Exception as e:
                raise ConnectionError(f"Failed to establish connection: {e}") from e

        # 3. Store connection reference (keyed by tunnel name)
        self._connections[config.tunnel_name] = connection

        # 4. Subscribe to state changes if supported
        if hasattr(connection, 'subscribe'):
            try:
                subscriber = _StateChangeHandler(config.tunnel_name, self)
                connection.subscribe(subscriber)
                self._subscribers[config.tunnel_name] = subscriber
                logger.debug(f"Subscribed to state changes for {config.tunnel_name}")
            except Exception as e:
                logger.warning(f"Could not subscribe to state changes: {e}")

        # 5. Wait for CONNECTED state (optional, configurable timeout)
        try:
            await self._wait_for_state(connection, ConnectionStateEnum.CONNECTED, timeout=30)
            logger.info(f"Connection to {server.server_name} established and connected")
        except asyncio.TimeoutError:
            await connection.close()
            self._connections.pop(config.tunnel_name, None)
            raise ConnectionError("Connection timeout - failed to reach CONNECTED state within 30 seconds")

        if progress_callback:
            progress_callback("connected")

        # 5. Get TUN device name
        # This method must exist on VPNConnection in the multi-tunnel daemon
        try:
            tun_device = connection.get_tun_device_name()
            logger.debug(f"TUN device: {tun_device}")
        except AttributeError:
            # Fallback for older single-tunnel daemon
            logger.warning("VPNConnection.get_tun_device_name() not available. Assuming 'proton0'. "
                          "This is incorrect for multi-tunnel setups!")
            tun_device = "proton0"

        # 6. Build Tunnel object (metadata should be serializable for D-Bus)
        tunnel = Tunnel(
            name=config.tunnel_name,
            adapter="proton",
            device=tun_device,
            namespace=None,  # Will be set by manager after calling routing strategy
            endpoint=server.server_name,
            connected_at=datetime.utcnow(),
            metadata={
                "protocol": config.protocol,
                "server_id": server.id,
                "server_country": config.country,
                "server_name": server.server_name,
                "entry_country": getattr(server, 'entry_country', None),
                "exit_country": getattr(server, 'exit_country', None),
            }
        )
        self._local_tunnels[config.tunnel_name] = tunnel

        logger.info(f"Tunnel '{config.tunnel_name}' created successfully (device: {tun_device})")
        return tunnel

    async def disconnect(self, tunnel: Tunnel) -> None:
        """
        Disconnect a Proton VPN tunnel.

        Args:
            tunnel: Tunnel to disconnect
        """
        tunnel_name = tunnel.name

        # Get connection from our internal tracking (primary method)
        connection = self._connections.get(tunnel_name)

        if connection:
            try:
                await connection.close()
                logger.info(f"Connection closed for tunnel '{tunnel_name}'")
            except Exception as e:
                logger.error(f"Error closing connection for {tunnel_name}: {e}")
                raise ConnectionError(f"Failed to disconnect: {e}") from e
        else:
            # Try to disconnect via connector (for multi-tunnel)
            try:
                if hasattr(self.connector, 'disconnect'):
                    await self.connector.disconnect(tunnel_name)
                    logger.info(f"Disconnected tunnel '{tunnel_name}' via connector")
            except Exception as e:
                raise TunnelNotFoundError(f"Tunnel '{tunnel_name}' not found or already disconnected: {e}")

        # Clean up tracking
        self._local_tunnels.pop(tunnel_name, None)
        self._connections.pop(tunnel_name, None)

        # Unsubscribe from state changes if we subscribed
        if tunnel_name in self._subscribers:
            # If connection has unsubscribe method, use it
            if connection and hasattr(connection, 'unsubscribe'):
                try:
                    connection.unsubscribe(self._subscribers[tunnel_name])
                except Exception:
                    pass
            self._subscribers.pop(tunnel_name, None)

    async def get_status(self, tunnel: Tunnel) -> TunnelStatus:
        """
        Get connection status.

        Args:
            tunnel: Tunnel to query

        Returns:
            TunnelStatus
        """
        tunnel_name = tunnel.name
        connection = self._connections.get(tunnel_name)

        if not connection:
            # No active connection tracking means tunnel not connected
            return TunnelStatus.DISCONNECTED

        try:
            state = connection.get_connection_state()
            # Map ConnectionStateEnum to TunnelStatus
            state_map = {
                ConnectionStateEnum.DISCONNECTED: TunnelStatus.DISCONNECTED,
                ConnectionStateEnum.CONNECTING: TunnelStatus.CONNECTING,
                ConnectionStateEnum.CONNECTED: TunnelStatus.CONNECTED,
                ConnectionStateEnum.DISCONNECTING: TunnelStatus.DISCONNECTING,
                ConnectionStateEnum.ERROR: TunnelStatus.ERROR,
            }
            status = state_map.get(state, TunnelStatus.ERROR)
            logger.debug(f"Tunnel '{tunnel_name}' status: {status.value}")
            return status
        except Exception as e:
            logger.error(f"Error getting status for {tunnel.name}: {e}")
            return TunnelStatus.ERROR

    def list_tunnels(self) -> List[Tunnel]:
        """
        List all tunnels managed by this adapter.

        Returns:
            List of Tunnel objects
        """
        return list(self._local_tunnels.values())

    def get_capabilities(self) -> AdapterCapabilities:
        """
        Return Proton VPN capabilities.

        NOTE: These reflect the current daemon capabilities.
        With multi-tunnel daemon, multi_tunnel will be True and max_tunnels will be higher.
        """
        # Base capabilities
        caps = AdapterCapabilities(
            supports_protocols=["wireguard", "openvpn-udp", "openvpn-tcp"],
            supports_kill_switch=True,
            supports_dns_isolation=True,  # Proton provides DNS per connection
            multi_tunnel=self._is_multi_tunnel,
        )

        # Set max_tunnels based on capability
        if self._is_multi_tunnel:
            # With multi-tunnel connector, can have many tunnels
            # The daemon should define a limit; we'll use a reasonable default
            caps.max_tunnels = 10  # TODO: Get from daemon if available
            caps.supports_per_app_routing = True  # With namespaces, per-app works
        else:
            # Single-tunnel limitation
            caps.max_tunnels = 1
            caps.supports_per_app_routing = False

        logger.debug(f"Reporting capabilities: {caps}")
        return caps

    async def get_traffic_stats(
        self, tunnel: Tunnel
    ) -> Tuple[int, int]:
        """
        Get traffic statistics for a tunnel.

        Args:
            tunnel: Tunnel object

        Returns:
            (bytes_in, bytes_out)
        """
        tunnel_name = tunnel.name
        connection = self._connections.get(tunnel_name)
        if not connection:
            raise TunnelNotFoundError(f"Tunnel '{tunnel_name}' has no active connection")

        try:
            # Try to get traffic stats from connection
            # Expected methods: get_bytes_received(), get_bytes_sent()
            # or get_traffic_stats() returning object with .received, .sent
            if hasattr(connection, 'get_traffic_stats'):
                stats = connection.get_traffic_stats()
                if hasattr(stats, 'received') and hasattr(stats, 'sent'):
                    return (stats.received, stats.sent)
                elif isinstance(stats, (list, tuple)) and len(stats) == 2:
                    return tuple(stats)
            elif hasattr(connection, 'get_bytes_received') and hasattr(connection, 'get_bytes_sent'):
                bytes_in = connection.get_bytes_received()
                bytes_out = connection.get_bytes_sent()
                return (bytes_in, bytes_out)

            # Placeholder - return zeros if API not available
            logger.debug(f"Traffic stats API not available for {tunnel_name}, returning zeros")
            return (0, 0)
        except Exception as e:
            logger.error(f"Failed to get traffic stats for {tunnel_name}: {e}")
            raise ConnectionError(f"Failed to get traffic stats: {e}") from e

    async def cleanup(self) -> None:
        """
        Cleanup all connections on daemon shutdown.
        """
        logger.info("Cleaning up all Proton VPN connections")

        # Disconnect all tunnels
        for tunnel_name, tunnel in list(self._local_tunnels.items()):
            try:
                await self.disconnect(tunnel)
            except Exception as e:
                logger.error(f"Error disconnecting tunnel {tunnel_name}: {e}")

        self._local_tunnels.clear()
        self._connections.clear()
        self._subscribers.clear()

        # If we have a connector with disconnect_all, use it
        if self.connector and hasattr(self.connector, 'disconnect_all'):
            try:
                await self.connector.disconnect_all()
                logger.info("Called connector.disconnect_all()")
            except Exception as e:
                logger.warning(f"Connector.disconnect_all() failed: {e}")

        logger.info("ProtonVPNAdapter cleanup complete")

    # Optional: Helper methods specific to Proton

    async def get_network_config(self, tunnel: Tunnel) -> Tuple[str, List[str]]:
        """
        Get network configuration for a tunnel (gateway and DNS).

        This is used by the routing strategy to configure the namespace.
        The connection should provide the VPN-assigned gateway IP and DNS servers.

        Args:
            tunnel: Tunnel object

        Returns:
            (gateway_ip, [dns_servers])

        Raises:
            TunnelNotFoundError: If tunnel not found
            ConfigurationError: If network config cannot be determined
        """
        tunnel_name = tunnel.name
        connection = self._connections.get(tunnel_name)
        if not connection:
            raise TunnelNotFoundError(f"Tunnel '{tunnel_name}' not connected")

        gateway = None
        dns_servers = []

        # Try to get gateway IP
        if hasattr(connection, 'get_gateway_ip'):
            try:
                gateway = connection.get_gateway_ip()
                logger.debug(f"Got gateway from connection: {gateway}")
            except Exception as e:
                logger.warning(f"Could not get gateway IP: {e}")

        # Try to get DNS servers
        if hasattr(connection, 'get_dns_servers'):
            try:
                dns_servers = connection.get_dns_servers()
                if isinstance(dns_servers, list):
                    logger.debug(f"Got DNS servers from connection: {dns_servers}")
                else:
                    logger.warning(f"get_dns_servers returned non-list: {type(dns_servers)}")
                    dns_servers = []
            except Exception as e:
                logger.warning(f"Could not get DNS servers: {e}")

        # Fallback values if methods not available or failed
        if not gateway:
            # Use typical OpenVPN/WireGuard gateway
            gateway = "10.7.0.1"  # FIXME: This is a guess; need actual value from daemon
            logger.debug(f"Using fallback gateway: {gateway}")

        if not dns_servers:
            # Use Proton's default DNS
            dns_servers = ["1.1.1.1", "1.0.0.1"]  # FIXME: Should get from connection/proton config
            logger.debug(f"Using fallback DNS: {dns_servers}")

        return (gateway, dns_servers)


class _StateChangeHandler:
    """
    Internal helper to handle VPN connection state changes.

    Subscribes to VPNConnection events and updates TunnelManager.
    """

    def __init__(self, tunnel_name: str, adapter: ProtonVPNAdapter):
        self.tunnel_name = tunnel_name
        self.adapter = adapter

    def state_updated(self, state: ConnectionStateEnum, connection: VPNConnection):
        """Callback from VPNStateSubscriber."""
        # Map state to TunnelStatus
        status_map = {
            ConnectionStateEnum.DISCONNECTED: TunnelStatus.DISCONNECTED,
            ConnectionStateEnum.CONNECTING: TunnelStatus.CONNECTING,
            ConnectionStateEnum.CONNECTED: TunnelStatus.CONNECTED,
            ConnectionStateEnum.DISCONNECTING: TunnelStatus.DISCONNECTING,
            ConnectionStateEnum.ERROR: TunnelStatus.ERROR,
        }
        status = status_map.get(state, TunnelStatus.ERROR)

        logger.info(f"Tunnel '{self.tunnel_name}' state changed to {status.value}")
        # Note: The manager should query adapter.get_status(tunnel) to get current status.
        # State changes are logged; D-Bus signals will be emitted by the manager
        # when it polls status or receives an event.
