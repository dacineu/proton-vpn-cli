"""Session management for multiple VPN users and backends."""

from .base import Session, SessionInfo, SessionNotFoundError, SessionExpiredError
from .dummy import DummySession
from .proton import ProtonSession
from .psiphon import PsiphonSession
from .wireguard import WireGuardSession
from .manager import SessionManager

__all__ = [
    "Session",
    "SessionInfo",
    "SessionNotFoundError",
    "SessionExpiredError",
    "DummySession",
    "ProtonSession",
    "PsiphonSession",
    "WireGuardSession",
    "SessionManager",
]
