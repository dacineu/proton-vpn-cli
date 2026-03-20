"""Dummy session for testing with the DummyAdapter."""

import json
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, Dict, Optional

from .base import Session, SessionInfo


@dataclass
class DummySession(Session):
    """A dummy session that is always valid.

    Used for testing multi-tunnel functionality without real VPN credentials.
    """
    adapter: str = "dummy"
    session_name: str = ""
    username: str = ""
    created_at: Optional[datetime] = None
    metadata: Dict[str, Any] = field(default_factory=dict)

    def __post_init__(self):
        if self.created_at is None:
            self.created_at = datetime.utcnow()

    async def validate(self) -> bool:
        """Dummy sessions never expire."""
        return True

    async def refresh(self):
        """No refresh needed."""
        pass

    async def revoke(self):
        """No revocation needed."""
        pass

    def to_dict(self) -> Dict[str, Any]:
        """Serialize to dictionary."""
        return {
            "adapter": self.adapter,
            "session_name": self.session_name,
            "username": self.username,
            "created_at": self.created_at.isoformat() if self.created_at else None,
            "metadata": self.metadata,
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "DummySession":
        """Deserialize from dictionary."""
        created_at = data.get("created_at")
        if created_at:
            if isinstance(created_at, str):
                created_at = datetime.fromisoformat(created_at)
            else:
                created_at = None
        return cls(
            adapter=data.get("adapter", "dummy"),
            session_name=data.get("session_name", ""),
            username=data.get("username", ""),
            created_at=created_at,
            metadata=data.get("metadata", {}),
        )

    def to_session_info(self) -> SessionInfo:
        """Convert to SessionInfo for listing."""
        return SessionInfo(
            adapter=self.adapter,
            session_name=self.session_name,
            username=self.username,
            valid_until=None,  # never expires
            status="active",
            metadata=self.metadata,
        )

    @classmethod
    async def create(
        cls,
        session_name: str,
        username: str,
        password: str = "",
        twofa_code: Optional[str] = None,
        **kwargs
    ) -> "DummySession":
        """
        Create a new dummy session.
        For dummy, no credentials are needed; just create the session.
        """
        # Password is ignored but accepted for compatibility
        session = cls(
            session_name=session_name,
            username=username,
            metadata={"created_by": username, "dummy": True},
        )
        return session
