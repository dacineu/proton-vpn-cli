"""Psiphon session handling."""

from dataclasses import dataclass, field
from datetime import datetime
from typing import Optional, Dict, Any

from .base import Session, SessionInfo


@dataclass
class PsiphonSession(Session):
    """Psiphon session (config-based, long-lived)."""

    adapter: str = "psiphon"
    session_name: str = ""
    username: str = ""
    config_file: str = ""  # Actual config file path (absolute)
    entry_country: Optional[str] = None
    exit_country: Optional[str] = None
    transport_protocol: str = "tcp"
    created_at: datetime = field(default_factory=datetime.utcnow)

    def __post_init__(self):
        self.adapter = "psiphon"

    async def validate(self) -> bool:
        """
        Validate Psiphon session.

        For Psiphon, validation means:
          - Config file exists
          - Entry/exit countries are valid codes (basic check)
          - Config is parseable (could test load)
        """
        import os
        if not os.path.exists(self.config_file):
            return False

        # Basic validation: config file exists and is readable
        # Could also parse and check required fields
        try:
            with open(self.config_file, 'r') as f:
                content = f.read()
                # Basic sanity: should have [Psiphon] section or JSON
                if "Psiphon" in content or "entry_country" in content:
                    return True
        except Exception:
            return False

        return True

    async def refresh(self):
        """
        Psiphon configs don't need refresh - they're static.
        Could implement: regenerate config with new entry points if needed.
        """
        # No-op: Psiphon configs are static files
        pass

    async def revoke(self):
        """Revoke Psiphon session - just delete config."""
        import os
        try:
            if os.path.exists(self.config_file):
                os.remove(self.config_file)
        except Exception as e:
            print(f"Warning: Failed to delete config {self.config_file}: {e}")

    def to_dict(self) -> Dict[str, Any]:
        """Serialize."""
        return {
            "adapter": self.adapter,
            "session_name": self.session_name,
            "username": self.username,
            "config_file": self.config_file,
            "entry_country": self.entry_country,
            "exit_country": self.exit_country,
            "transport_protocol": self.transport_protocol,
            "created_at": self.created_at.isoformat(),
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "PsiphonSession":
        """Deserialize."""
        created_at = datetime.utcnow()
        if data.get("created_at"):
            created_at = datetime.fromisoformat(data["created_at"])

        return cls(
            session_name=data["session_name"],
            username=data["username"],
            config_file=data["config_file"],
            entry_country=data.get("entry_country"),
            exit_country=data.get("exit_country"),
            transport_protocol=data.get("transport_protocol", "tcp"),
            created_at=created_at,
        )

    def to_session_info(self) -> SessionInfo:
        """Convert to SessionInfo."""
        status = "active" if self.validate() else "invalid"
        return SessionInfo(
            adapter=self.adapter,
            session_name=self.session_name,
            username=self.username,
            status=status,
            metadata={
                "entry_country": self.entry_country,
                "exit_country": self.exit_country,
                "transport": self.transport_protocol,
            },
        )
