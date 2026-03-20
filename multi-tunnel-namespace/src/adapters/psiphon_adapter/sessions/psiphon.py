"""Psiphon session handling."""

from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Optional, Dict, Any

from libvpnmanager.sessions.base import Session, SessionInfo, SessionExpiredError


@dataclass
class PsiphonSession(Session):
    """Psiphon session - manages config and possibly credentials."""

    adapter: str = "psiphon"
    session_name: str = ""
    username: str = ""
    config_file: str = ""  # Path to Psiphon config
    created_at: datetime = field(default_factory=datetime.utcnow)

    def __post_init__(self):
        self.adapter = "psiphon"

    async def validate(self) -> bool:
        """Check if config file exists."""
        return Path(self.config_file).exists()

    async def refresh(self):
        """Psiphon config doesn't typically refresh."""
        if not await self.validate():
            raise SessionExpiredError("Psiphon config not found")

    async def revoke(self):
        """Psiphon doesn't have explicit revoke; delete config."""
        try:
            if self.config_file:
                Path(self.config_file).unlink(missing_ok=True)
        except Exception as e:
            print(f"Warning: failed to delete Psiphon config: {e}")

    def to_dict(self) -> Dict[str, Any]:
        return {
            "adapter": self.adapter,
            "session_name": self.session_name,
            "username": self.username,
            "config_file": self.config_file,
            "created_at": self.created_at.isoformat(),
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "PsiphonSession":
        created_at = datetime.utcnow()
        if data.get("created_at"):
            from datetime import datetime as _dt
            created_at = _dt.fromisoformat(data["created_at"])

        return cls(
            session_name=data["session_name"],
            username=data["username"],
            config_file=data.get("config_file", ""),
            created_at=created_at,
        )

    @classmethod
    async def create(
        cls,
        session_name: str,
        username: str,
        password: Optional[str] = None,
        **kwargs
    ) -> "PsiphonSession":
        """
        Psiphon session creation: generates a config file.

        The 'password' could be used as a config file path or as
        parameters to generate a new config. For simplicity, we
        expect an existing Psiphon config file.
        """
        config_file = password or kwargs.get("config_file", "")
        if not config_file:
            raise ValueError(
                "Psiphon requires a config file path as 'password' parameter"
            )

        config_path = Path(config_file)
        if not config_path.exists():
            raise FileNotFoundError(f"Psiphon config not found: {config_file}")

        return cls(
            session_name=session_name,
            username=username,
            config_file=str(config_path.absolute()),
        )

    def to_session_info(self) -> SessionInfo:
        status = "active" if self.validate() else "invalid"
        return SessionInfo(
            adapter=self.adapter,
            session_name=self.session_name,
            username=self.username,
            status=status,
            metadata={"config_file": self.config_file},
        )
