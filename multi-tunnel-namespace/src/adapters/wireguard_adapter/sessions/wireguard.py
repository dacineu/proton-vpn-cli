"""WireGuard session handling."""

from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional, Dict, Any

from libvpnmanager.sessions.base import Session, SessionInfo


@dataclass
class WireGuardSession(Session):
    """WireGuard session - just points to a config file."""

    adapter: str = "wireguard"
    session_name: str = ""
    username: str = ""
    config_file: str = ""  # Path to .conf file
    private_key: str = ""
    created_at: datetime = field(default_factory=datetime.utcnow)

    def __post_init__(self):
        self.adapter = "wireguard"

    async def validate(self) -> bool:
        """Check if config file exists."""
        return Path(self.config_file).exists()

    async def refresh(self):
        """WireGuard config doesn't refresh."""
        if not await self.validate():
            raise Exception("WireGuard config file not found")

    async def revoke(self):
        """No revoke for static config."""
        pass

    def to_dict(self) -> Dict[str, Any]:
        return {
            "adapter": self.adapter,
            "session_name": self.session_name,
            "username": self.username,
            "config_file": self.config_file,
            "private_key": self.private_key,
            "created_at": self.created_at.isoformat(),
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "WireGuardSession":
        created_at = datetime.utcnow()
        if data.get("created_at"):
            from datetime import datetime as _dt
            created_at = _dt.fromisoformat(data["created_at"])

        return cls(
            session_name=data["session_name"],
            username=data["username"],
            config_file=data.get("config_file", ""),
            private_key=data.get("private_key", ""),
            created_at=created_at,
        )

    @classmethod
    async def create(
        cls,
        session_name: str,
        username: str,
        password: Optional[str] = None,
        **kwargs
    ) -> "WireGuardSession":
        """
        WireGuard doesn't have login. Instead, expect a config file.

        The session is created by pointing to an existing .conf file.
        The 'password' parameter should be the path to the config file.
        """
        config_file = password or kwargs.get("config_file", "")
        if not config_file:
            raise ValueError(
                "WireGuard requires a config file path as 'password' parameter"
            )

        config_path = Path(config_file)
        if not config_path.exists():
            raise FileNotFoundError(f"WireGuard config not found: {config_file}")

        # Parse config to extract private key (optional for metadata)
        private_key = ""
        try:
            with open(config_path, 'r') as f:
                for line in f:
                    if line.strip().startswith("PrivateKey"):
                        _, private_key = line.strip().split("=", 1)
                        private_key = private_key.strip()
                        break
        except Exception:
            pass

        return cls(
            session_name=session_name,
            username=username,
            config_file=str(config_path.absolute()),
            private_key=private_key,
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
