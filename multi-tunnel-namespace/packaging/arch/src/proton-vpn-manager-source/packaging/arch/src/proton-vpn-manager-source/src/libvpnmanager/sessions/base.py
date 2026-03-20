"""Base session abstraction."""

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from datetime import datetime
from typing import Optional, Dict, Any


@dataclass
class SessionInfo:
    """Summary of a session for listing."""
    adapter: str
    session_name: str
    username: str
    valid_until: Optional[datetime] = None
    status: str = "active"  # "active", "expired", "invalid"
    metadata: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        """Convert to a dictionary for D-Bus serialization."""
        result = {
            "adapter": self.adapter,
            "session_name": self.session_name,
            "username": self.username,
            "status": self.status,
            "metadata": self.metadata,
        }
        if self.valid_until is not None:
            # Convert datetime to ISO format string for D-Bus
            result["valid_until"] = self.valid_until.isoformat()
        else:
            result["valid_until"] = ""
        return result


class SessionError(Exception):
    """Base session error."""
    pass


class SessionNotFoundError(SessionError):
    """Session not found."""
    pass


class SessionExpiredError(SessionError):
    """Session has expired."""
    pass


class Session(ABC):
    """
    Abstract base class for a VPN session.

    A session represents authenticated credentials for a specific VPN backend.
    It can be:
      - Proton: OAuth tokens, cookies
      - Psiphon: Config with API keys
      - WireGuard: Static config file path (no auth needed)
    """

    adapter: str = "base"  # Override in subclasses
    session_name: str = ""
    username: str = ""

    @abstractmethod
    async def validate(self) -> bool:
        """
        Check if this session is still valid (not expired).

        Returns:
            True if session can be used, False if needs refresh or re-login
        """
        pass

    @abstractmethod
    async def refresh(self):
        """
        Refresh session if possible (e.g., use refresh token).

        Raises:
            SessionExpiredError: If refresh fails, needs re-login
        """
        pass

    @abstractmethod
    async def revoke(self):
        """
        Revoke this session on the server (log out).
        Should invalidate tokens so they can't be used again.
        """
        pass

    @abstractmethod
    def to_dict(self) -> Dict[str, Any]:
        """Serialize session to dictionary for storage."""
        pass

    @classmethod
    @abstractmethod
    def from_dict(cls, data: Dict[str, Any]) -> "Session":
        """Deserialize session from dictionary."""
        pass

    def get_adapter(self) -> str:
        """Return the adapter type this session is for."""
        return self.adapter

    def get_owner(self) -> str:
        """Return the OS username who owns this session."""
        return self.username

    def get_name(self) -> str:
        """Return the user-defined session name."""
        return self.session_name
