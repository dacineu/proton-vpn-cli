"""VPN Adapter abstract base class and capabilities."""

from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import List, Tuple, Optional

from ..models.tunnel import Tunnel
from ..models.status import TunnelStatus
from ..models.config import ConnectionConfig


@dataclass
class AdapterCapabilities:
    """
    Describes the capabilities of a VPN adapter.

    Attributes:
        multi_tunnel: Whether the adapter can create multiple concurrent tunnels
        supports_protocols: List of supported protocol names
        max_tunnels: Maximum concurrent tunnels (None = unlimited)
        supports_per_app_routing: Native per-application routing support
        supports_kill_switch: Network lock/kill switch capability
        supports_dns_isolation: Per-tunnel DNS configuration
    """

    multi_tunnel: bool = False
    supports_protocols: List[str] = None
    max_tunnels: Optional[int] = None
    supports_per_app_routing: bool = False
    supports_kill_switch: bool = False
    supports_dns_isolation: bool = False

    def __post_init__(self):
        if self.supports_protocols is None:
            self.supports_protocols = []


class VPNAdapter(ABC):
    """
    Abstract base class for VPN adapters.

    Each VPN backend (Proton, Psiphon, WireGuard) implements this interface
    to provide connection management independent of routing strategy.

    Lifecycle:
        1. Adapter instantiated by TunnelManager
        2. connect() called with config → returns Tunnel object
        3. Tunnel is registered with manager
        4. get_status() and get_traffic_stats() called periodically
        5. disconnect() called when user stops tunnel
        6. destroy_tunnel() triggers cleanup in routing layer
        7. cleanup() called on daemon shutdown
    """

    @abstractmethod
    async def connect(
        self,
        config: ConnectionConfig,
        progress_callback: Optional[callable] = None,
    ) -> Tunnel:
        """
        Establish a VPN connection.

        Args:
            config: Connection configuration (type-specific subclass)
            progress_callback: Optional callable(status: str) for progress updates

        Returns:
            Tunnel object with populated fields (device, namespace, etc.)

        Raises:
            ConfigurationError: If config is invalid
            AuthenticationError: If credentials are invalid
            ConnectionError: If network/server unreachable
            CapabilityError: If feature not supported
        """
        pass

    @abstractmethod
    async def disconnect(self, tunnel: Tunnel) -> None:
        """
        Disconnect an active tunnel.

        Args:
            tunnel: Tunnel object to disconnect

        Raises:
            TunnelNotFoundError: If tunnel not managed by this adapter
        """
        pass

    @abstractmethod
    async def get_status(self, tunnel: Tunnel) -> TunnelStatus:
        """
        Get current connection status.

        Args:
            tunnel: Tunnel object

        Returns:
            TunnelStatus enum value
        """
        pass

    @abstractmethod
    async def list_tunnels(self) -> List[Tunnel]:
        """
        List all tunnels currently managed by this adapter.

        This includes both connected and disconnected tunnels that
        haven't been destroyed yet.

        Returns:
            List of Tunnel objects
        """
        pass

    @abstractmethod
    def get_capabilities(self) -> AdapterCapabilities:
        """
        Return the capabilities of this adapter.

        Returns:
            AdapterCapabilities object
        """
        pass

    @abstractmethod
    async def get_traffic_stats(
        self, tunnel: Tunnel
    ) -> Tuple[int, int]:
        """
        Get traffic statistics for a tunnel.

        Args:
            tunnel: Tunnel object

        Returns:
            (bytes_in, bytes_out) tuple

        Raises:
            TunnelNotFoundError: If tunnel not found
        """
        pass

    @abstractmethod
    async def cleanup(self) -> None:
        """
        Cleanup all resources on daemon shutdown.

        Should disconnect all active tunnels and release any resources.
        After this, the adapter should not be used.
        """
        pass

    # Optional: Helper methods

    def get_adapter_name(self) -> str:
        """
        Return the canonical name of this adapter.

        Default implementation uses class name.
        Override for custom naming.
        """
        return self.__class__.__name__.lower().replace("adapter", "")
