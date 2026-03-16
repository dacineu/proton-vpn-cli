"""Proton VPN session handling."""

from dataclasses import dataclass, field
from datetime import datetime, timedelta
from typing import Optional, Dict, Any

from .base import Session, SessionInfo, SessionExpiredError
from ..models.exceptions import AuthenticationError


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
        """
        Check if session is still valid.

        A session is valid if:
          - expires_at is in the future (with small buffer)
          - Or we can use refresh_token to get new access token
        """
        if self.expires_at is None:
            return False

        # Check with 5-minute buffer
        now = datetime.utcnow()
        if self.expires_at > now + timedelta(minutes=5):
            return True

        # Expired or about to expire
        return False

    async def refresh(self):
        """
        Refresh the access token using refresh_token.

        Raises:
            SessionExpiredError: If refresh fails (user must re-login)
        """
        try:
            # This would call Proton API refresh endpoint
            # For now, we need to implement this with actual proton-vpn-api-core
            # The API likely has a method to set external session tokens

            # Pseudocode:
            # api = ProtonVPNAPI(metadata)
            # await api.login_with_session(self.refresh_token)
            # new_tokens = api.get_session_tokens()
            # self.access_token = new_tokens.access_token
            # self.refresh_token = new_tokens.refresh_token
            # self.expires_at = datetime.utcnow() + timedelta(seconds=new_tokens.expires_in)

            # For now, assume refresh would work if we had daemon support
            raise NotImplementedError(
                "Proton session refresh requires proton-vpn-api-core integration"
            )

        except Exception as e:
            raise SessionExpiredError(f"Failed to refresh session: {e}") from e

    async def revoke(self):
        """Revoke session on Proton servers."""
        # Call Proton API to revoke refresh token
        # This logs out the session
        try:
            # Pseudocode:
            # api = ProtonVPNAPI(metadata)
            # await api.revoke_session(self.refresh_token)
            pass
        except Exception as e:
            print(f"Warning: Failed to revoke session: {e}")

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
