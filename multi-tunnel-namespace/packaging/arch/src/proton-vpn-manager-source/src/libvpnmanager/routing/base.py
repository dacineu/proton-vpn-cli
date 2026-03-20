"""Routing strategy base class."""

from abc import ABC, abstractmethod
from typing import Dict, Set, Optional


class RoutingStrategy(ABC):
    """
    Abstract base class for routing strategies.

    A routing strategy defines how tunnel traffic is isolated and routed.
    Options include network namespaces (Option 1) and policy routing (Option 2).
    """

    @abstractmethod
    async def create_tunnel_context(self, tunnel_name: str) -> dict:
        """
        Create routing context for a new tunnel.

        Args:
            tunnel_name: Unique tunnel identifier

        Returns:
            Dictionary of routing metadata to attach to Tunnel object
            (e.g., {"namespace": "vpn_work"} or {"table": 1001, "mark": 0x3e9})
        """
        pass

    @abstractmethod
    async def destroy_tunnel_context(self, tunnel_name: str, metadata: dict) -> None:
        """
        Destroy routing context for a tunnel.

        Args:
            tunnel_name: Tunnel identifier
            metadata: Routing metadata returned from create_tunnel_context
        """
        pass

    @abstractmethod
    async def assign_process_to_tunnel(
        self, tunnel_name: str, metadata: dict, pid: int
    ) -> None:
        """
        Assign a process to a tunnel's routing context.

        Args:
            tunnel_name: Tunnel identifier
            metadata: Routing metadata
            pid: Process ID to assign
        """
        pass

    @abstractmethod
    async def list_active_tunnels(self) -> Dict[str, dict]:
        """
        List currently active tunnel routing contexts.

        Returns:
            Dict mapping tunnel_name → routing metadata
        """
        pass

    @abstractmethod
    async def cleanup_all(self) -> None:
        """Clean up all routing contexts on shutdown."""
        pass
