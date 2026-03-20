"""Mock implementation of proton.vpn.core.session_holder.ClientTypeMetadata."""

from dataclasses import dataclass


@dataclass
class ClientTypeMetadata:
    """Metadata about the client type for API initialization."""
    type: str
    version: str
