"""WireGuard session (static config)."""

from dataclasses import dataclass, field
from datetime import datetime
from typing import Optional, Dict, Any

from .base import Session, SessionInfo


@dataclass
class WireGuardSession(Session):
    """WireGuard session - just a reference to a config file."""

    adapter: str = "wireguard"
    session_name: str = ""
    username: str = ""
    config_file: str = ""  # Absolute path to wg-quick config
    interface_name: Optional[str] = None  # Override interface from config
    created_at: datetime = field(default_factory=datetime.utcnow)

    def __post_init__(self):
        self.adapter = "wireguard"

    async def validate(self) -> bool:
        """Check if WireGuard config file exists and is valid."""
        import os
        if not os.path.exists(self.config_file):
            return False

        # Basic: check if it's a valid WireGuard config format
        try:
            with open(self.config_file, 'r') as f:
                content = f.read()
                # Should have [Interface] and [Peer] sections
                if "[Interface]" in content and "[Peer]" in content:
                    return True
        except Exception:
            return False

        return False

    async def refresh(self):
        """WireGuard configs don't need refresh."""
        pass

    async def revoke(self):
        """Delete config file (if we created it)."""
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
            "interface_name": self.interface_name,
            "created_at": self.created_at.isoformat(),
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "WireGuardSession":
        """Deserialize."""
        created_at = datetime.utcnow()
        if data.get("created_at"):
            created_at = datetime.fromisoformat(data["created_at"])

        return cls(
            session_name=data["session_name"],
            username=data["username"],
            config_file=data["config_file"],
            interface_name=data.get("interface_name"),
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
            metadata={"config_file": self.config_file},
        )
