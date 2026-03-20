"""Routing strategies."""

from .base import RoutingStrategy
from .namespace import NetworkNamespaceRouting

__all__ = [
    "RoutingStrategy",
    "NetworkNamespaceRouting",
]
