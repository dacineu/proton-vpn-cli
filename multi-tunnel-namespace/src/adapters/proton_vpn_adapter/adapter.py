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

from libvpnmanager.models.tunnel import Tunnel
from libvpnmanager.models.status import TunnelStatus
from libvpnmanager.models.config import ProtonConnectionConfig
from libvpnmanager.models.exceptions import (
    ConnectionError,
    AuthenticationError,
    ConfigurationError,
    TunnelNotFoundError,
    CapabilityError,
    AdapterError,
)

from libvpnmanager.adapters.base import VPNAdapter, AdapterCapabilities

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

    def __init__(self, session=None):
        """
        Initialize adapter.

        Args:
            session: ProtonSession instance (optional, for credentials)
        """
        if not IMPORTS_AVAILABLE:
            raise ImportError(
                "proton-vpn-api-core is not installed. "
                "This adapter requires the proton.vpn.core package."
            )

        self.session = session
        self.api: Optional[ProtonVPNAPI] = None
        self.connector: Optional[VPNConnector] = None
        self._is_multi_tunnel: bool = False
        self._local_tunnels: Dict[str, Tunnel] = {}
        self._connections: Dict[str, VPNConnection] = {}
        self._subscribers: Dict[str, callable] = {}
        self._lock = asyncio.Lock()

    def register_status_callback(self, tunnel_name: str, callback: callable):
        """Register a callback for status changes on a specific tunnel."""
        if tunnel_name not in self._status_callbacks:
            self._status_callbacks[tunnel_name] = []
        if callback not in self._status_callbacks[tunnel_name]:
            self._status_callbacks[tunnel_name].append(callback)
            logger.debug(f"Registered status callback for tunnel '{tunnel_name}'")

    async def _ensure_api(self):
        """Ensure API object is initialized."""
        if self.api is None:
            self.api = ProtonVPNAPI()
            # TODO: Need to set session tokens somehow
            # Possibly from a stored session or via login

    async def _ensure_connector(self):
        """Get or create a multi-tunnel connector."""
        await self._ensure_api()
        if self.connector is None:
            # Get a connector that supports multiple tunnels
            # This is the multi-tunnel connector that's key to the design
            self.connector = self.api.get_multi_tunnel_connector()
            self._is_multi_tunnel = True
        return self.connector

    async def _find_server(self, config: ProtonConnectionConfig) -> LogicalServer:
        """
        Resolve a LogicalServer from the API based on config.

        Args:
            config: Proton connection configuration

        Returns:
            LogicalServer instance

        Raises:
            ConfigurationError: If no server matches criteria
        """
        await self._ensure_api()
        server_list = self.api.get_server_list()

        # Prefer explicit server_id if provided
        if config.server_id:
            server = server_list.get_by_id(config.server_id)
            if server:
                return server
            raise ConfigurationError(f"Server ID '{config.server_id}' not found")

        # Fall back to country-based selection
        if config.country:
            servers = server_list.filter_by_country(config.country)
            if servers:
                # TODO: Could apply additional filters (load, features, etc.)
                # For now, pick the first available
                return servers[0]
            raise ConfigurationError(f"No servers available in country '{config.country}'")

        raise ConfigurationError("Must specify server_id or country in configuration")

    @property
    def capabilities(self) -> AdapterCapabilities:
        """Return Proton adapter capabilities."""
        return AdapterCapabilities(
            multi_tunnel=True,
            supports_protocols=["wireguard", "openvpn-udp", "openvpn-tcp"],
            max_tunnels=10,  # Proton allows ~10 simultaneous devices
            supports_per_app_routing=False,
            supports_kill_switch=True,
            supports_dns_isolation=True,
        )

    async def connect(
        self,
        config: ProtonConnectionConfig,
        progress_callback: Optional[callable] = None,
    ) -> Tunnel:
        """
        Establish a Proton VPN connection.

        Args:
            config: Proton-specific connection configuration
            progress_callback: Optional callable(status: str) for progress updates

        Returns:
            Tunnel object with populated fields

        Raises:
            ConfigurationError: Invalid config
            AuthenticationError: Not logged in or tokens invalid
            ConnectionError: Network/server issue
            CapabilityError: Feature not supported
        """
        await self._ensure_connector()

        tunnel_name = config.tunnel_name
        # Resolve the target server from configuration
        server = await self._find_server(config)
        logger.info(f"Connecting Proton tunnel '{tunnel_name}' to {server.server_name}")

        try:
            # Establish connection via multi-tunnel connector
            # The connector should accept tunnel_name to identify the connection
            connection = await self.connector.connect(
                tunnel_name=tunnel_name,
                server=server,
                protocol=config.protocol,
            )

            # Wait for connection to be established
            async for status in connection.monitor():
                if progress_callback:
                    progress_callback(status.message)

            # Get TUN device name (the connector should provide this)
            device = connection.get_tun_device_name()
            if not device:
                raise ConnectionError("Connected but no TUN device found")

            # Extract network configuration from connection
            # These methods are expected on the multi-tunnel connector's connection object.
            try:
                gateway = connection.get_gateway_ip()
                dns_servers = connection.get_dns_servers()
                vpn_ip = connection.get_assigned_ip()
            except AttributeError as e:
                raise ConnectionError(f"Connection object missing required network config method: {e}")

            # Build Tunnel object
            tunnel = Tunnel(
                name=tunnel_name,
                adapter="proton",
                session_name=config.session_name,
                username=self.session.username,  # from session credentials
                device=device,
                namespace=None,  # Will be set by routing layer
                endpoint=connection.get_endpoint(),
                connected_at=datetime.now(),
                gateway=gateway,
                dns_servers=dns_servers,
                vpn_ip=vpn_ip,
                metadata={
                    "connection_id": connection.id,
                    "server": server,
                    "protocol": config.protocol,
                },
            )

            async with self._lock:
                self._local_tunnels[tunnel_name] = tunnel
                self._connections[tunnel_name] = connection

            logger.info(f"Proton tunnel '{tunnel_name}' connected on device {device}")
            return tunnel

        except Exception as e:
            logger.error(f"Failed to connect Proton tunnel '{tunnel_name}': {e}")
            if isinstance(e, (AuthenticationError, ConnectionError, ConfigurationError)):
                raise
            raise ConnectionError(f"Proton connection failed: {e}") from e

    async def create_tunnel(self, name: str, config: dict) -> Tunnel:
        """
        Convenience method to create a tunnel by name and config dict.
        Constructs ProtonConnectionConfig and calls connect().
        """
        # Build ProtonConnectionConfig from config dict
        cfg_dict = dict(config)
        cfg_dict['tunnel_name'] = name
        cfg_dict['adapter'] = 'proton'
        proton_cfg = ProtonConnectionConfig.from_dict(cfg_dict)
        return await self.connect(proton_cfg)

    async def destroy_tunnel(self, name: str) -> None:
        """
        Destroy a tunnel by name. Looks up tunnel from _local_tunnels and disconnects.
        """
        tunnel = self._local_tunnels.get(name)
        if not tunnel:
            raise TunnelNotFoundError(f"Tunnel {name} not found")
        await self.disconnect(tunnel)

    async def disconnect(self, tunnel: Tunnel) -> None:
        """
        Disconnect a Proton tunnel.

        Args:
            tunnel: Tunnel object to disconnect
        """
        tunnel_name = tunnel.name
        async with self._lock:
            connection = self._connections.pop(tunnel_name, None)
            self._local_tunnels.pop(tunnel_name, None)

        if connection:
            try:
                await connection.disconnect()
                logger.info(f"Disconnected Proton tunnel '{tunnel_name}'")
            except Exception as e:
                logger.warning(f"Error disconnecting Proton tunnel {tunnel_name}: {e}")

    async def get_status(self, tunnel: Tunnel) -> TunnelStatus:
        """
        Get Proton connection status.

        Args:
            tunnel: Tunnel object

        Returns:
            TunnelStatus enum value
        """
        connection = self._connections.get(tunnel.name)
        if not connection:
            return TunnelStatus.DISCONNECTED

        try:
            state = connection.get_state()
            # Map connection state to TunnelStatus
            if state == ConnectionStateEnum.CONNECTED:
                return TunnelStatus.CONNECTED
            elif state == ConnectionStateEnum.CONNECTING:
                return TunnelStatus.CONNECTING
            elif state == ConnectionStateEnum.DISCONNECTING:
                return TunnelStatus.DISCONNECTING
            elif state == ConnectionStateEnum.ERROR:
                return TunnelStatus.ERROR
            else:
                return TunnelStatus.DISCONNECTED
        except Exception as e:
            logger.error(f"Error getting status for tunnel {tunnel.name}: {e}")
            return TunnelStatus.ERROR

    async def get_traffic_stats(
        self, tunnel: Tunnel
    ) -> Tuple[int, int]:
        """
        Get traffic statistics for a Proton tunnel.

        Args:
            tunnel: Tunnel object

        Returns:
            Tuple of (bytes_in, bytes_out)
        """
        connection = self._connections.get(tunnel.name)
        if not connection:
            return (0, 0)

        try:
            stats = connection.get_statistics()
            return (stats.bytes_in, stats.bytes_out)
        except Exception as e:
            logger.error(f"Error getting traffic stats for {tunnel.name}: {e}")
            return (0, 0)

    async def list_tunnels(self) -> List[Tunnel]:
        """List all active Proton tunnels."""
        # Return list of tunnels currently managed by this adapter.
        # Currently, self._connections maps tunnel_name to connection.
        # We'll construct Tunnel objects from connection information.
        tunnels = []
        for tunnel_name, connection in self._connections.items():
            # The connection likely has methods to get status, device, etc.
            # For now, return minimal Tunnel proxy.
            # We'll need to have Tunnel attributes like name, adapter, device, etc.
            # This is incomplete; actual implementation requires querying connection.
            tunnel = Tunnel(
                name=tunnel_name,
                adapter="proton",
                session_name="",  # not tracked here
                username="",      # not tracked
                device=getattr(connection, 'device', ''),
                endpoint=getattr(connection, 'endpoint', ''),
                connected_at=datetime.now(),
                metadata={"server": getattr(connection, 'server', None)},
            )
            tunnels.append(tunnel)
        return tunnels

    async def get_capabilities(self) -> AdapterCapabilities:
        """Return Proton adapter capabilities."""
        return self.capabilities

    async def cleanup(self):
        """Clean up all Proton connections on shutdown."""
        logger.info("Cleaning up Proton adapter...")
        # Disconnect all active tunnels
        for tunnel_name in list(self._connections.keys()):
            connection = self._connections.pop(tunnel_name)
            try:
                await connection.disconnect()
            except Exception as e:
                logger.warning(f"Error disconnecting {tunnel_name} during cleanup: {e}")

        # Logout from API
        if self.api:
            try:
                # The core might have a logout method
                await self.api.logout()
            except Exception as e:
                logger.debug(f"API logout (ignored): {e}")

        self._local_tunnels.clear()
        self._connections.clear()
        logger.info("Proton adapter cleanup complete")
