"""Session manager: stores and retrieves sessions for multiple users/adapters."""

import asyncio
import json
import os
from datetime import datetime
from pathlib import Path
from typing import Dict, Tuple, List, Optional

from .base import Session, SessionInfo
from .dummy import DummySession
from .proton import ProtonSession
from .psiphon import PsiphonSession
from .wireguard import WireGuardSession
from ..models.exceptions import AuthenticationError, SessionNotFoundError


class SessionManager:
    """
    Manages multiple VPN sessions for multiple users and adapter types.

    Responsibilities:
      - Load/save sessions from persistent storage
      - Validate sessions (expiry, config existence)
      - Refresh sessions when needed
      - Provide adapter-specific Session objects
      - Support listing/removing sessions

    Storage layout:
      $XDG_DATA_HOME/protonvpn/sessions/
        ├── proton/
        │   └── {session_name}.json  (encrypted with user's keyring)
        ├── psiphon/
        │   └── {session_name}.json
        └── wireguard/
            └── {session_name}.conf  (or .json pointer)
    """

    SESSION_TYPES = {
        "dummy": DummySession,
        "proton": ProtonSession,
        "psiphon": PsiphonSession,
        "wireguard": WireGuardSession,
    }

    def __init__(self, data_dir: Optional[str] = None):
        """
        Initialize SessionManager.

        Args:
            data_dir: Override default data directory (for testing)
        """
        if data_dir is None:
            data_dir = os.path.join(
                os.environ.get("XDG_DATA_HOME", os.path.expanduser("~/.local/share")),
                "protonvpn",
                "sessions"
            )
        self.data_dir = Path(data_dir)
        self._sessions: Dict[Tuple[str, str, str], Session] = {}
        self._lock = asyncio.Lock()

    async def load_session(
        self,
        adapter: str,
        session_name: str,
        username: str,
        password: Optional[str] = None,
        twofa_code: Optional[str] = None
    ) -> Session:
        """
        Load or create a session.

        Args:
            adapter: Adapter type ("proton", "psiphon", "wireguard")
            session_name: User-defined session identifier
            username: OS username who owns this session
            password: Optional password for initial login (if session doesn't exist)

        Returns:
            Session object

        Raises:
            SessionNotFoundError: If session doesn't exist and no password
            AuthenticationError: If credentials invalid
        """
        key = (adapter, session_name, username)
        async with self._lock:
            # Already loaded?
            if key in self._sessions:
                session = self._sessions[key]
                # Validate
                if not await session.validate():
                    # Needs refresh or re-login
                    try:
                        await session.refresh()
                    except Exception as e:
                        # Refresh failed - remove session
                        self._sessions.pop(key, None)
                        raise AuthenticationError(f"Session expired: {e}") from e
                return session

            # Not loaded - try storage
            session = await self._load_from_storage(adapter, session_name, username)
            if session:
                # Validate
                if not await session.validate():
                    try:
                        await session.refresh()
                    except Exception as e:
                        raise AuthenticationError(f"Session expired: {e}") from e
                self._sessions[key] = session
                return session

            # No stored session
            if password is None:
                raise SessionNotFoundError(
                    f"Session '{session_name}' not found for user '{username}'. "
                    "Provide password to create new session."
                )

            # Create new session by logging in
            session = await self._create_session(
                adapter, session_name, username, password, twofa_code
            )
            self._sessions[key] = session
            await self._save_to_storage(session)
            return session

    async def get_connector(
        self,
        adapter: str,
        session_name: str,
        username: str
    ) -> "MultiTunnelVPNConnector":
        """
        Get a multi-tunnel connector for a specific session.

        This method will be called by TunnelManager to get an adapter-specific
        connector that uses the given session's credentials.

        Args:
            adapter: Adapter type
            session_name: Session identifier
            username: OS user

        Returns:
            MultiTunnelVPNConnector configured with that session
        """
        # Ensure session exists
        session = await self.load_session(adapter, session_name, username)

        # Create/get connector for this session
        # Note: Connector needs to be per-session, not shared,
        # because each session has different credentials
        key = (adapter, session_name, username, "connector")
        if key not in self._sessions:
            connector = MultiTunnelVPNConnector(adapter, session)
            self._sessions[key] = connector
        return self._sessions[key]

    async def list_sessions(
        self,
        adapter: Optional[str] = None,
        username: Optional[str] = None
    ) -> List[SessionInfo]:
        """
        List available sessions.

        Args:
            adapter: Filter by adapter type (None = all)
            username: Filter by OS username (None = all)

        Returns:
            List of SessionInfo objects
        """
        sessions = []

        # Scan storage directories
        adapters_to_check = [adapter] if adapter else list(self.SESSION_TYPES.keys())

        for adapter_type in adapters_to_check:
            session_dir = self.data_dir / adapter_type
            if not session_dir.exists():
                continue

            # Find session files
            if adapter_type == "wireguard":
                # WireGuard uses .conf files directly
                pattern = "*.conf"
            else:
                pattern = "*.json"

            for filepath in session_dir.glob(pattern):
                # Parse filename to get session_name
                session_name = filepath.stem

                # Determine the file's owner (OS user who owns the session file)
                file_owner = filepath.owner()

                # Load minimally to get SessionInfo
                try:
                    if adapter_type == "wireguard":
                        # WireGuard uses .conf files directly; no JSON
                        session_username = file_owner
                        data = None
                    else:
                        # For proton, psiphon, dummy, etc.: read JSON
                        with open(filepath, 'r') as f:
                            data = json.load(f)
                        session_username = data.get("username", file_owner)

                    if username and session_username != username:
                        continue

                    # Create temporary session object just for info
                    session_cls = self.SESSION_TYPES[adapter_type]
                    session = session_cls.from_dict(
                        data if adapter_type != "wireguard" else {
                            "session_name": session_name,
                            "username": session_username,
                            "config_file": str(filepath),
                        }
                    )
                    info = session.to_session_info()
                    sessions.append(info)

                except Exception as e:
                    print(f"Warning: failed to load session {filepath}: {e}")
                    continue

        print(f"DEBUG list_sessions: returning {len(sessions)} sessions: {[s.session_name for s in sessions]}", flush=True)
        return sessions

    async def logout(
        self,
        adapter: str,
        session_name: str,
        username: str
    ) -> bool:
        """
        Remove a session (revoke if possible, delete storage).

        Args:
            adapter: Adapter type
            session_name: Session name
            username: OS user

        Returns:
            True if session was removed
        """
        key = (adapter, session_name, username)
        async with self._lock:
            # Get session if loaded
            session = self._sessions.pop(key, None)
            if not session:
                # Try to load to get file path
                try:
                    session = await self._load_from_storage(adapter, session_name, username)
                except Exception:
                    pass

            if session:
                # Revoke on server
                try:
                    await session.revoke()
                except Exception as e:
                    print(f"Warning: failed to revoke session: {e}")

                # Delete from storage
                await self._delete_from_storage(adapter, session_name, username)
                return True

            return False

    async def cleanup_user_sessions(self, username: str):
        """
        Remove all sessions for a user (on logout).

        Called when a user logs out of the system or explicitly logs out of all.
        """
        async with self._lock:
            keys_to_remove = [
                key for key in self._sessions.keys()
                if key[2] == username  # username matches
            ]
            for key in keys_to_remove:
                adapter, session_name, _ = key
                session = self._sessions.pop(key)
                try:
                    await session.revoke()
                except Exception:
                    pass
                try:
                    await self._delete_from_storage(adapter, session_name, username)
                except Exception:
                    pass

    # Internal storage methods

    async def _load_from_storage(
        self,
        adapter: str,
        session_name: str,
        username: str
    ) -> Optional[Session]:
        """Load session from disk."""
        if adapter not in self.SESSION_TYPES:
            return None

        session_dir = self.data_dir / adapter
        if not session_dir.exists():
            return None

        # Try to find file
        if adapter == "wireguard":
            # WireGuard configs: could be {session_name}.conf or {username}_{session_name}.conf
            candidates = [
                session_dir / f"{session_name}.conf",
                session_dir / f"{username}_{session_name}.conf",
            ]
            for filepath in candidates:
                if filepath.exists():
                    data = {
                        "session_name": session_name,
                        "username": username,
                        "config_file": str(filepath),
                    }
                    session_cls = self.SESSION_TYPES[adapter]
                    return session_cls.from_dict(data)
        else:
            # JSON sessions: {session_name}.json or {username}_{session_name}.json
            candidates = [
                session_dir / f"{session_name}.json",
                session_dir / f"{username}_{session_name}.json",
            ]
            for filepath in candidates:
                if filepath.exists():
                    with open(filepath, 'r') as f:
                        data = json.load(f)
                    # Verify username matches
                    if data.get("username") != username:
                        continue
                    session_cls = self.SESSION_TYPES[adapter]
                    return session_cls.from_dict(data)

        return None

    async def _save_to_storage(self, session: Session):
        """Save session to disk."""
        adapter = session.get_adapter()
        session_name = session.get_name()
        username = session.get_owner()

        session_dir = self.data_dir / adapter
        session_dir.mkdir(parents=True, exist_ok=True)

        if adapter == "wireguard":
            # For WireGuard, session just points to config file
            # The config file should already exist (user provided)
            # We just create a pointer file if needed
            data = session.to_dict()
            pointer_file = session_dir / f"{username}_{session_name}.json"
            with open(pointer_file, 'w') as f:
                json.dump(data, f, indent=2)
        else:
            # JSON session (encrypted in future)
            data = session.to_dict()
            filepath = session_dir / f"{username}_{session_name}.json"
            with open(filepath, 'w') as f:
                json.dump(data, f, indent=2)

    async def _delete_from_storage(
        self,
        adapter: str,
        session_name: str,
        username: str
    ):
        """Delete session from disk."""
        adapter_dir = self.data_dir / adapter
        if not adapter_dir.exists():
            return

        if adapter == "wireguard":
            # Delete the actual config file if we own it
            candidates = [
                adapter_dir / f"{session_name}.conf",
                adapter_dir / f"{username}_{session_name}.conf",
            ]
            for filepath in candidates:
                if filepath.exists():
                    filepath.unlink()
            # Also delete pointer JSON
            pointer = adapter_dir / f"{username}_{session_name}.json"
            if pointer.exists():
                pointer.unlink()
        else:
            filepath = adapter_dir / f"{username}_{session_name}.json"
            if filepath.exists():
                filepath.unlink()

    async def _create_session(
        self,
        adapter: str,
        session_name: str,
        username: str,
        password: str,
        twofa_code: Optional[str] = None
    ) -> Session:
        """
        Create a new session by logging in.

        This is the login flow for each adapter.
        """
        if adapter == "dummy":
            # Dummy adapter accepts any credentials and creates a session
            # Password can be anything; we ignore it.
            return DummySession(
                adapter=adapter,
                session_name=session_name,
                username=username,
                metadata={"login_password_provided": bool(password)},
            )
        elif adapter == "proton":
            # Use proton-vpn-api-core to login
            # Need to implement actual login
            raise NotImplementedError(
                "Proton login requires proton-vpn-api-core integration"
            )
        elif adapter == "psiphon":
            # Psiphon might use config file generation
            # Could call psiphon binary to generate config
            raise NotImplementedError("Psiphon login not implemented")
        elif adapter == "wireguard":
            # WireGuard doesn't have login - config file must exist
            raise AuthenticationError(
                "WireGuard requires existing config file. Use --config option."
            )
        else:
            raise ValueError(f"Unknown adapter: {adapter}")
