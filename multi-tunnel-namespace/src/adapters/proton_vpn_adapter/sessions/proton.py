"""Proton VPN session handling."""

from dataclasses import dataclass, field
from datetime import datetime, timedelta
from typing import Optional, Dict, Any

from libvpnmanager.sessions.base import Session, SessionInfo, SessionExpiredError
from libvpnmanager.models.exceptions import AuthenticationError


@dataclass
class ProtonSession(Session):
    """Proton VPN session with OAuth tokens."""

    adapter: str = "proton"
    session_name: str = ""
    username: str = ""  # Proton account email
    access_token: str = ""
    refresh_token: str = ""
    expires_at: Optional[datetime] = None
    cookies: Dict[str, str] = field(default_factory=dict)
    created_at: datetime = field(default_factory=datetime.utcnow)

    def __post_init__(self):
        """Ensure adapter type is set."""
        self.adapter = "proton"

    async def validate(self) -> bool:
        """Check if session is still valid."""
        if self.expires_at is None:
            return False

        now = datetime.utcnow()
        if self.expires_at > now + timedelta(minutes=5):
            return True

        return False

    async def refresh(self):
        """Refresh the access token using refresh_token."""
        raise NotImplementedError(
            "Proton session refresh requires proton-vpn-api-core integration"
        )

    async def revoke(self):
        """Revoke session on Proton servers."""
        pass  # TODO: Implement with actual API

    def to_dict(self) -> Dict[str, Any]:
        """Serialize to dictionary."""
        return {
            "adapter": self.adapter,
            "session_name": self.session_name,
            "username": self.username,
            "access_token": self.access_token,
            "refresh_token": self.refresh_token,
            "expires_at": self.expires_at.isoformat() if self.expires_at else None,
            "cookies": self.cookies,
            "created_at": self.created_at.isoformat(),
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "ProtonSession":
        """Deserialize from dictionary."""
        expires_at = None
        if data.get("expires_at"):
            expires_at = datetime.fromisoformat(data["expires_at"])

        created_at = datetime.utcnow()
        if data.get("created_at"):
            created_at = datetime.fromisoformat(data["created_at"])

        return cls(
            session_name=data["session_name"],
            username=data["username"],
            access_token=data["access_token"],
            refresh_token=data["refresh_token"],
            expires_at=expires_at,
            cookies=data.get("cookies", {}),
            created_at=created_at,
        )

    @classmethod
    async def create(
        cls,
        session_name: str,
        username: str,
        password: str,
        twofa_code: Optional[str] = None,
        **kwargs
    ) -> "ProtonSession":
        """
        Create a new Proton session by logging in.

        This requires proton-vpn-api-core to be available.
        """
        # This would integrate with proton-vpn-api-core
        raise NotImplementedError(
            "Proton login requires proton-vpn-api-core integration"
        )

    def to_session_info(self) -> SessionInfo:
        """Convert to SessionInfo for listing."""
        status = "active" if self.validate() else "expired"
        return SessionInfo(
            adapter=self.adapter,
            session_name=self.session_name,
            username=self.username,
            valid_until=self.expires_at,
            status=status,
            metadata={"protocols": ["wireguard", "openvpn-udp", "openvpn-tcp"]},
        )
