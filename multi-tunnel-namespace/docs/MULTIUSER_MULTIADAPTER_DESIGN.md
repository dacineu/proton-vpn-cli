# Enhanced Design: Multi-User, Multi-Backend Tunnel Management

**Date**: 2026-03-16
**Goal**: Support multiple Proton VPN users (sessions) and multiple VPN backends simultaneously

---

## 1. Problem Statement

Current design limitations:
1. **Single session per daemon**: All tunnels share the same Proton account/session
2. **No user selection**: Can't have Alice's work Proton account and Bob's personal Proton account active simultaneously
3. **Backend locked to one**: If you create a Proton tunnel, all tunnels are Proton (could mix with Psiphon, WireGuard)

**Desired workflow**:

```bash
# As user alice (in her desktop session):
$ protonvpn tunnel create work --adapter proton --session alice_work --country US
$ protonvpn tunnel create personal --adapter proton --session alice_personal --country JP

# As user bob (different OS user, same system):
$ protonvpn tunnel create gaming --adapter psiphon --session bob_psiphon --exit-country DE
$ protonvpn tunnel create travel --adapter wireguard --session bob_wireguard --config /path/wg.conf

# List all tunnels from all users/sessions:
$ protonvpn tunnel list --all-users
NAME            ADAPTER    SESSION         STATUS   ENDPOINT
work            proton     alice_work     connected us-proton.example.com
personal        proton     alice_personal connected jp-proton.example.com
gaming          psiphon    bob_psiphon    connected psiphon123.de
travel          wireguard  bob_wireguard  connected wg-server.example.com

# Any user can switch to any tunnel (if permitted by policy):
$ protonvpn tunnel switch work      # Alice uses her work tunnel
$ protonvpn tunnel switch gaming    # Bob can use his psiphon tunnel
```

---

## 2. Key Insights

### 2.1 Session Identity

A **session** is:
- For Proton: authenticated credentials (session token, cookies) scoped to a Proton account
- For Psiphon: maybe a credential/entry point configuration
- For WireGuard: static config file (no session needed, but we can call it a "session" for consistency)

**Each tunnel** is associated with:
- **Adapter type**: "proton", "psiphon", "wireguard", etc.
- **Session identifier**: Unique name chosen by user (e.g., "alice_work", "bob_personal")
- **Connection config**: country, protocol, server, etc.

### 2.2 Session Store

We need a **session store** that can hold multiple sessions for each adapter type:

```python
class SessionStore:
    """
    Persists and retrieves sessions for different users/adapter types.

    Storage backends:
      - For Proton: Encrypted keyring entries per user
      - For Psiphon: Config files in ~/.config/protonvpn/psiphon/
      - For WireGuard: Static config files (no session)
    """
    def get_session(adapter: str, session_name: str, username: str) -> Session:
        """Load session for specific adapter+session+user."""
        pass

    def save_session(adapter: str, session_name: str, username: str, session: Session):
        """Persist session."""
        pass

    def list_sessions(adapter: str, username: str) -> List[SessionInfo]:
        """List available sessions for user."""
        pass
```

---

## 3. Enhanced Architecture

### 3.1 Component Diagram

```
┌─────────────────────────────────────────────────────────────────────┐
│                         protonvpn CLI                              │
│  $ protonvpn tunnel create work --adapter proton --session alice_work
│  $ protonvpn tunnel list --all-users
│  $ protonvpn tunnel switch work
└───────────────────────────────┬─────────────────────────────────────┘
                                │ D-Bus
┌───────────────────────────────▼─────────────────────────────────────┐
│                    proton-vpn-manager daemon                        │
│  ┌───────────────────────────────────────────────────────────────┐  │
│  │                      SessionManager                           │  │
│  │  ┌─────────────────────────────────────────────────────────┐  │  │
│  │  │ Session Store: {                                        │  │  │
│  │  │   (adapter, session_name, username) → SessionData      │  │  │
│  │  │   ("proton", "alice_work", "alice") → tokens, cookies  │  │  │
│  │  │   ("proton", "bob_personal", "bob") → ...              │  │  │
│  │  │   ("psiphon", "bob_psiphon", "bob") → config           │  │  │
│  │  │   ("wireguard", "bob_wg", "bob") → wg.conf path        │  │  │
│  │  │ }                                                        │  │  │
│  │  └─────────────────────────────────────────────────────────┘  │  │
│  │                                                               │  │
│  │  For each session, can create MultiTunnelVPNConnector:       │  │
│  │    (see note below)                                          │  │
│  │                                                               │  │
│  └───────────────────────────────────────────────────────────────┘  │
│                                                                     │
│  ┌───────────────────────────────────────────────────────────────┐  │
│  │                      AdapterFactory                           │  │
│  │  Creates appropriate VPNAdapter based on adapter type        │  │
│  │    get_adapter("proton", session) → ProtonVPNAdapter        │  │
│  │    get_adapter("psiphon", session) → PsiphonAdapter        │  │
│  │    get_adapter("wireguard", session) → WireGuardAdapter    │  │
│  └───────────────────────────────────────────────────────────────┘  │
│                                                                     │
│  ┌───────────────────────────────────────────────────────────────┐  │
│  │               TunnelManager (unchanged)                       │  │
│  │  Tunnels: Dict[name → Tunnel]                                 │  │
│  │    "work" → Tunnel(adapter="proton", session="alice_work")  │  │
│  │    "gaming" → Tunnel(adapter="psiphon", session="bob_psiphon")│ │
│  │    "travel" → Tunnel(adapter="wireguard", session="bob_wg") │  │
│  └───────────────────────────────────────────────────────────────┘  │
│                                                                     │
│  ┌───────────────────────────────────────────────────────────────┐  │
│  │         NetworkNamespaceRouting (unchanged)                   │  │
│  │  Creates vpn_work, vpn_gaming, vpn_travel namespaces         │  │
│  └───────────────────────────────────────────────────────────────┘  │
│                                                                     │
│  (TUN devices created by respective adapters)                      │
└─────────────────────────────────────────────────────────────────────┘

NOTE on MultiTunnelVPNConnector per session:
  - Each (adapter, session) pair needs its own connector
    because each has different credentials.
  - But we can have multiple tunnels using the SAME session!
    Example: alice_work session → can create multiple tunnels to different
    countries (US, UK, CA) using same alice account.
  - So: SessionManager.get_connector(adapter, session) returns a
    MultiTunnelVPNConnector that uses that specific session.
```

---

## 4. Data Model Changes

### 4.1 Enhanced Tunnel

```python
@dataclass
class Tunnel:
    name: str
    adapter: str                    # "proton", "psiphon", "wireguard"
    session_name: str               # User-defined session identifier
    username: str                   # OS user who created this tunnel
    device: str                     # TUN device: "tun0", "proton0", etc.
    namespace: Optional[str] = None
    endpoint: Optional[str] = None
    connected_at: Optional[datetime] = None
    bytes_in: int = 0
    bytes_out: int = 0
    metadata: Dict[str, Any] = field(default_factory=dict)
```

**New fields**:
- `session_name`: Which session this tunnel uses
- `username`: Which OS user owns this tunnel (for per-user filtering)

### 4.2 Session abstraction

```python
class Session:
    """Base class for a VPN session."""
    adapter: str
    session_name: str
    username: str
    credentials: Any  # Encrypted tokens, config path, etc.

    async def validate(self) -> bool:
        """Check if session is still valid (not expired)."""
        pass

    async def refresh(self):
        """Refresh session if possible."""
        pass
```

**ProtonSession**:
```python
@dataclass
class ProtonSession(Session):
    adapter: str = "proton"
    session_name: str = ""
    username: str = ""
    access_token: str = ""
    refresh_token: str = ""
    expires_at: Optional[datetime] = None
    cookies: Dict[str, str] = field(default_factory=dict)
```

**PsiphonSession**:
```python
@dataclass
class PsiphonSession(Session):
    adapter: str = "psiphon"
    session_name: str = ""
    username: str = ""
    config_file: str = ""  # Path to psiphon config
    entry_sponsor_id: Optional[str] = None
```

**WireGuardSession**:
```python
@dataclass
class WireGuardSession(Session):
    adapter: str = "wireguard"
    session_name: str = ""
    username: str = ""
    config_file: str = ""  # Path to wg-quick config
```

---

## 5. SessionManager Implementation

```python
class SessionManager:
    """
    Manages multiple sessions for multiple users and adapters.

    Responsibilities:
      - Load/save sessions from secure storage (keyring, files)
      - Create/validate/refresh sessions
      - Provide adapter-specific connectors that use specific sessions
    """

    def __init__(self):
        # (adapter, session_name, username) → Session object
        self._sessions: Dict[Tuple[str, str, str], Session] = {}
        self._connectors: Dict[Tuple[str, str, str], MultiTunnelVPNConnector] = {}
        self._lock = asyncio.Lock()

    async def load_session(
        self,
        adapter: str,
        session_name: str,
        username: str,
        password: Optional[str] = None  # For initial login
    ) -> Session:
        """
        Load or create a session.

        Args:
            adapter: "proton", "psiphon", etc.
            session_name: User-defined name (e.g., "alice_work")
            username: OS username (who owns this session)
            password: Optional password for initial login (if session doesn't exist)

        Returns:
            Session object

        Raises:
            SessionNotFoundError: If session doesn't exist and no password
            AuthenticationError: If credentials invalid
        """
        key = (adapter, session_name, username)
        async with self._lock:
            if key in self._sessions:
                # Already loaded
                session = self._sessions[key]
                # Check if still valid
                if not await session.validate():
                    # Expired, need refresh
                    await session.refresh()
                return session

            # Not loaded - try to load from storage
            stored = await self._load_from_storage(adapter, session_name, username)
            if stored:
                self._sessions[key] = stored
                if not await stored.validate():
                    await stored.refresh()
                return stored

            # No stored session - need to create with password
            if password is None:
                raise SessionNotFoundError(
                    f"Session {session_name} for {username} not found. "
                    "Provide password to create."
                )

            # Create new session by logging in
            session = await self._create_session(adapter, session_name, username, password)
            self._sessions[key] = session
            await self._save_to_storage(session)
            return session

    async def get_connector(
        self,
        adapter: str,
        session_name: str,
        username: str
    ) -> MultiTunnelVPNConnector:
        """
        Get or create a connector for a specific session.

        Args:
            adapter: Adapter type
            session_name: Session identifier
            username: OS user

        Returns:
            MultiTunnelVPNConnector configured to use that session
        """
        key = (adapter, session_name, username)
        async with self._lock:
            if key in self._connectors:
                return self._connectors[key]

            # Need to ensure session exists
            session = await self.load_session(adapter, session_name, username)
            # Create connector
            connector = MultiTunnelVPNConnector(adapter, session)
            self._connectors[key] = connector
            return connector

    async def list_available_sessions(
        self,
        adapter: Optional[str] = None,
        username: Optional[str] = None
    ) -> List[SessionInfo]:
        """
        List sessions that are available for creating tunnels.

        This returns stored sessions (even if daemon hasn't loaded them yet).

        Args:
            adapter: Filter by adapter type
            username: Filter by OS user (None = all users)

        Returns:
            List of SessionInfo (adapter, session_name, username, valid_until)
        """
        # Scan storage directories
        sessions = []
        # For each adapter type, look in its storage location
        # For Proton: keyring entries with prefix "protonvpn:session:"
        # For Psiphon: ~/.config/protonvpn/psiphon/*.json
        # For WireGuard: ~/.config/protonvpn/wireguard/*.conf
        # ... return list
        return sessions

    async def logout(self, adapter: str, session_name: str, username: str):
        """Remove a session (invalidate and delete stored credentials)."""
        key = (adapter, session_name, username)
        async with self._lock:
            if key in self._connectors:
                connector = self._connectors.pop(key)
                await connector.disconnect_all()  # Clean up any tunnels
            if key in self._sessions:
                session = self._sessions.pop(key)
                # Invalidate on server if possible
                try:
                    await session.revoke()
                except Exception:
                    pass
            # Delete from storage
            await self._delete_from_storage(adapter, session_name, username)

    # Private helpers (to be implemented based on storage backend)

    async def _load_from_storage(self, adapter, session_name, username) -> Optional[Session]:
        """Load session from persistent storage."""
        pass

    async def _save_to_storage(self, session: Session):
        """Save session to persistent storage."""
        pass

    async def _delete_from_storage(self, adapter, session_name, username):
        """Delete session from storage."""
        pass
```

---

## 6. Modified ProtonVPNAdapter

Now the adapter needs to work with **sessions** rather than creating its own `ProtonVPNAPI`:

```python
class ProtonVPNAdapter(VPNAdapter):
    """
    Proton VPN adapter that uses a Session object.

    This adapter can be instantiated multiple times with different sessions.
    Each session represents a different Proton account/user.
    """

    def __init__(self, session: ProtonSession):
        """
        Initialize adapter with a specific session.

        Args:
            session: ProtonSession (contains credentials, may be encrypted)
        """
        self.session = session
        self.api: Optional[ProtonVPNAPI] = None
        self.connector: Optional[MultiTunnelVPNConnector] = None
        self._local_tunnels: Dict[str, Tunnel] = {}

    async def _ensure_api(self):
        """Initialize ProtonVPNAPI with this session's credentials."""
        if self.api is None:
            # Create API with session tokens
            metadata = ClientTypeMetadata(
                type="linux-cli",
                version="0.1.8"
            )
            self.api = ProtonVPNAPI(metadata)
            # Inject session tokens directly or via login
            # Need to check how ProtonVPNAPI accepts external sessions
            await self.api._set_session(self.session.access_token, self.session.refresh_token)
            # Or: await self.api.login_with_session(self.session)

    async def _ensure_connector(self):
        """Get or create multi-tunnel connector for this session."""
        await self._ensure_api()
        if self.connector is None:
            # Get multi-tunnel connector from API
            self.connector = await self.api.get_vpn_connector(multi_tunnel=True)

    async def connect(self, config: ProtonConnectionConfig, progress_callback=None) -> Tunnel:
        """
        Connect a tunnel using THIS adapter's session.

        The tunnel will be associated with:
          adapter = "proton"
          session_name = self.session.session_name
          username = self.session.username
        """
        await self._ensure_connector()

        # Find server
        server = await self._find_server(config)

        # Connect using THIS session's connector
        connection = await self.connector.connect(
            tunnel_name=config.tunnel_name,
            server=server,
            protocol=config.protocol
        )
        await self._wait_for_state(connection, ConnectionStateEnum.CONNECTED)

        tun_device = connection.get_tun_device_name()

        # Build Tunnel with session info
        tunnel = Tunnel(
            name=config.tunnel_name,
            adapter="proton",
            session_name=self.session.session_name,
            username=self.session.username,
            device=tun_device,
            namespace=None,  # Set by manager
            endpoint=server.server_name,
            connected_at=datetime.utcnow(),
            metadata={
                "protocol": config.protocol,
                "server_id": server.id,
                "_connection": connection,  # Internal
            }
        )
        self._local_tunnels[config.tunnel_name] = tunnel
        return tunnel

    async def disconnect(self, tunnel: Tunnel) -> None:
        """Disconnect a tunnel."""
        connection = tunnel.metadata.get("_connection")
        if connection:
            await connection.close()
        self._local_tunnels.pop(tunnel.name, None)

    async def get_status(self, tunnel: Tunnel) -> TunnelStatus:
        """Get status."""
        connection = tunnel.metadata.get("_connection")
        if not connection:
            return TunnelStatus.DISCONNECTED
        state = connection.get_connection_state()
        # Map to TunnelStatus
        mapping = {...}
        return mapping[state]

    def list_tunnels(self) -> List[Tunnel]:
        """List tunnels managed by THIS adapter (i.e., this session)."""
        return list(self._local_tunnels.values())

    def get_capabilities(self) -> AdapterCapabilities:
        """Capabilities of Proton adapter."""
        return AdapterCapabilities(
            multi_tunnel=True,  # Now multi-tunnel!
            supports_protocols=["wireguard", "openvpn-udp", "openvpn-tcp"],
            max_tunnels=10,  # Proton allows ~10 devices
            supports_per_app_routing=False,
            supports_kill_switch=True,
            supports_dns_isolation=True,
        )

    async def get_traffic_stats(self, tunnel: Tunnel) -> Tuple[int, int]:
        """Get stats."""
        connection = tunnel.metadata.get("_connection")
        if not connection:
            raise TunnelNotFoundError(tunnel.name)
        # Get stats from connection
        stats = connection.get_traffic_stats()
        return (stats.rx_bytes, stats.tx_bytes)

    async def cleanup(self) -> None:
        """Disconnect all tunnels from this session."""
        for tunnel in list(self._local_tunnels.values()):
            try:
                await self.disconnect(tunnel)
            except Exception as e:
                print(f"Error disconnecting {tunnel.name}: {e}")
        self._local_tunnels.clear()
```

---

## 7. Modified TunnelManager for Multi-User

Now `TunnelManager` needs to be aware of sessions:

```python
class TunnelManager:
    def __init__(self, routing_strategy: RoutingStrategy, session_manager: SessionManager):
        self.routing = routing_strategy
        self.session_manager = session_manager
        self.adapters: Dict[Tuple[str, str], VPNAdapter] = {}
        # Key now: (adapter_type, session_name) → adapter instance
        self.tunnels: Dict[str, Tunnel] = {}
        self._lock = asyncio.Lock()

    def get_adapter(self, adapter: str, session_name: str, username: str) -> VPNAdapter:
        """
        Get or create adapter for given session.

        Args:
            adapter: "proton", "psiphon", etc.
            session_name: User-defined session identifier
            username: OS user who owns this

        Returns:
            VPNAdapter instance (shared among all tunnels using that session)
        """
        key = (adapter, session_name)
        if key not in self.adapters:
            # Need to create adapter
            if adapter == "proton":
                session = self.session_manager.load_session(
                    adapter, session_name, username
                )
                adapter_inst = ProtonVPNAdapter(session)
            elif adapter == "psiphon":
                session = self.session_manager.load_session(adapter, session_name, username)
                adapter_inst = PsiphonAdapter(session)
            elif adapter == "wireguard":
                session = self.session_manager.load_session(adapter, session_name, username)
                adapter_inst = WireGuardAdapter(session)
            else:
                raise AdapterNotFoundError(adapter)
            self.adapters[key] = adapter_inst
        return self.adapters[key]

    async def create_tunnel(self, config: ConnectionConfig, username: str) -> Tunnel:
        """
        Create a tunnel.

        Args:
            config: ConnectionConfig (includes adapter, tunnel_name, session_name)
            username: OS user requesting this tunnel
        """
        async with self._lock:
            if config.tunnel_name in self.tunnels:
                raise TunnelExistsError(config.tunnel_name)

            # Get adapter for this session
            adapter = self.get_adapter(
                config.adapter,
                config.session_name,  # NEW: session_name in config
                username
            )

            # Create tunnel object
            tunnel = Tunnel(
                name=config.tunnel_name,
                adapter=config.adapter,
                session_name=config.session_name,
                username=username,
                device="",
                metadata={"config": config.to_dict()},
            )
            self.tunnels[config.tunnel_name] = tunnel
            return tunnel

    async def connect_tunnel(self, tunnel_name: str, username: str) -> Tunnel:
        """Connect a tunnel."""
        async with self._lock:
            tunnel = self.tunnels.get(tunnel_name)
            if not tunnel:
                raise TunnelNotFoundError(tunnel_name)

            # Verify user owns this tunnel OR is admin
            if tunnel.username != username and not self._is_admin(username):
                raise PermissionError(f"Tunnel {tunnel_name} owned by {tunnel.username}")

            adapter = self.get_adapter(
                tunnel.adapter,
                tunnel.session_name,
                tunnel.username  # Use owner's username for session
            )

            config_dict = tunnel.metadata.get("config", {})
            config = ConnectionConfig.from_dict(config_dict)

            connected_tunnel = await adapter.connect(config)
            tunnel.device = connected_tunnel.device
            tunnel.namespace = connected_tunnel.namespace
            tunnel.endpoint = connected_tunnel.endpoint
            tunnel.connected_at = connected_tunnel.connected_at
            tunnel.metadata.update(connected_tunnel.metadata)

            # Create namespace
            routing_metadata = await self.routing.create_tunnel_context(tunnel_name)
            tunnel.namespace = routing_metadata.get("namespace")

            return tunnel

    async def list_tunnels(self, username: Optional[str] = None, all_users: bool = False) -> List[Tunnel]:
        """
        List tunnels.

        Args:
            username: If provided, only tunnels for that user (unless all_users=True)
            all_users: If True, ignore username filter (admin only)
        """
        async with self._lock:
            tunnels = list(self.tunnels.values())
            if all_users and self._is_admin(username):
                return tunnels
            if username:
                tunnels = [t for t in tunnels if t.username == username]
            return tunnels

    # ... other methods with username awareness
```

---

## 8. CLI Changes

### Enhanced `tunnel create` command

```bash
# Create a tunnel specifying adapter and session
$ protonvpn tunnel create work \
    --adapter proton \
    --session alice_work \
    --country US

# If session doesn't exist, prompt for credentials:
$ protonvpn tunnel create personal \
    --adapter proton \
    --session alice_personal \
    --country JP
Password for alice@protonmail.com: ****
2FA code: 123456
Session "alice_personal" saved.

# Psiphon example:
$ protonvpn tunnel create psiphon1 \
    --adapter psiphon \
    --session bob_psiphon \
    --entry-country US \
    --exit-country DE

# WireGuard example:
$ protonvpn tunnel create wg1 \
    --adapter wireguard \
    --session bob_wg \
    --config /home/bob/wg-work.conf
```

### `tunnel list` with user filtering

```bash
# Show only current user's tunnels
$ protonvpn tunnel list
NAME        ADAPTER    SESSION         STATUS
work        proton     alice_work     connected
personal    proton     alice_personal connected

# Show all tunnels (admin only)
$ protonvpn tunnel list --all-users
NAME        ADAPTER    OWNER       SESSION         STATUS
work        proton     alice       alice_work      connected
personal    proton     alice       alice_personal  connected
gaming      psiphon    bob         bob_psiphon     connected
travel      wireguard  bob         bob_wg          disconnected
```

### `tunnel sessions` command - list available sessions

```bash
$ protonvpn tunnel sessions --adapter proton
AVAILABLE SESSIONS (Proton):
  alice_work      (alice)     expires: 2026-03-23  Active
  alice_personal  (alice)     expires: 2026-03-23  Active
  bob_personal    (bob)       expires: 2026-03-20  Expired (needs re-login)

$ protonvpn tunnel sessions --all-adapters
ADAPTER    SESSION           OWNER     STATUS
proton     alice_work       alice     Active
proton     bob_personal     bob       Expired
psiphon    bob_psiphon      bob       Active
wireguard  bob_wg           bob       Config exists
```

### `tunnel login` command - create/refresh session

```bash
# Login with Proton and save as session
$ protonvpn tunnel login --adapter proton --session my_work --username alice@protonmail.com
Password: ****
2FA: 123456
Session "my_work" saved and ready to use.

# List sessions after login
$ protonvpn tunnel sessions
```

### `tunnel logout` - remove session

```bash
$ protonvpn tunnel logout --adapter proton --session alice_work
Session "alice_work" removed. Any active tunnels using it will disconnect.
```

---

## 9. Session Storage Design

### Storage Layout

```
$HOME/.local/share/protonvpn/
├── sessions/
│   ├── proton/
│   │   ├── alice_work.json         # Encrypted session tokens
│   │   ├── alice_personal.json
│   │   └── bob_personal.json
│   ├── psiphon/
│   │   ├── bob_psiphon.json        # Psiphon config + metadata
│   │   └── alice_psiphon.json
│   └── wireguard/
│       ├── bob_wg.conf             # WireGuard config file reference
│       └── alice_wg.conf
└── keyring/                         # System keyring integration
```

### Proton Session Storage

```json
{
  "adapter": "proton",
  "session_name": "alice_work",
  "username": "alice",
  "access_token": "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9...",
  "refresh_token": "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9...",
  "expires_at": "2026-03-16T12:00:00Z",
  "cookies": {
    "session": "abc123",
    "csrf": "xyz789"
  },
  "created_at": "2026-03-15T10:00:00Z"
}
```

**Encryption**: Use `proton-keyring-linux` to encrypt these files with user's login password or keyring.

### Psiphon Session Storage

```json
{
  "adapter": "psiphon",
  "session_name": "bob_psiphon",
  "username": "bob",
  "config": {
    "entry_country": "US",
    "exit_country": "DE",
    "transport_protocol": "tcp",
    "sponsor_id": "sponsor123"
  },
  "created_at": "2026-03-15T10:00:00Z"
}
```

### WireGuard Session Storage

Just a reference to the config file:

```ini
# This is a pointer file, not the actual WG config
adapter = wireguard
session_name = bob_wg
username = bob
config_file = /home/bob/.config/wireguard/work.conf
```

---

## 10. Security Considerations

### Access Control

**Policy**: A user can:
- Create tunnels using ANY session (even sessions created by other users) - for sharing
- But can only list/see all sessions if they are admin
- Can only destroy/ disconnect tunnels they created OR if they are admin

**Enforcement**:

```python
def _is_admin(self, username: str) -> bool:
    """Check if user is in sudo/wheel group."""
    import grp
    try:
        admin_groups = grp.getgrnam("sudo").gr_mem
        return username in admin_groups
    except KeyError:
        return False
```

### Session Encryption

Sessions containing credentials (Proton tokens, Psiphon config with API keys) must be:
- Encrypted at rest using user's login keyring
- Decrypted only when loading into memory
- Wiped from memory on logout

Use `keyring` library or `proton-keyring-linux` directly.

### Sandboxing

Daemon already runs with:
- CapabilityBoundingSet: CAP_NET_ADMIN, CAP_SYS_ADMIN
- PrivateTmp, ProtectSystem, etc.
- Should also use `ProtectHome=read-only` or `tmpfs` for session storage

---

## 11. Backward Compatibility

**Goal**: Old single-user Proton-only workflows still work.

**Strategy**:

1. Default behavior (no `--session` specified):
   ```bash
   protonvpn tunnel create mytunnel --country US
   ```
   Implies:
   - adapter = "proton" (default)
   - session = "default" (implicit session for current user)
   - First time: create session with current user's credentials

2. Single-session mode: If daemon detects only one user has sessions, can omit `--all-users` in list

3. Old `protonvpn connect` command:
   - Should still work as before (single tunnel, default session)
   - Internally uses this new system with session="default"

---

## 12. Implementation Plan

### Phase 1: Session Management (Week 1-2)

- [ ] Design session storage format (per adapter)
- [ ] Implement `Session` base class + `ProtonSession` subclass
- [ ] Create `SessionManager` with load/save/validate/refresh
- [ ] Integrate with keyring for encryption
- [ ] Write `protonvpn tunnel login` command
- [ ] Write `protonvpn tunnel logout` command
- [ ] Write `protonvpn tunnel sessions` command

### Phase 2: Multi-Session Adapters (Week 3-4)

- [ ] Modify `ProtonVPNAdapter` to accept `ProtonSession` instead of creating its own API
- [ ] Ensure `MultiTunnelVPNConnector` uses session credentials correctly
- [ ] Test: Two different Proton sessions on same daemon
- [ ] Implement `PsiphonAdapter` and `WireGuardAdapter` (simpler)
- [ ] Implement `AdapterFactory` in daemon

### Phase 3: Multi-User TunnelManager (Week 5-6)

- [ ] Update `TunnelManager` to track `username` and `session_name` per tunnel
- [ ] Add permission checks ( Ownership, admin override)
- [ ] Update `list_tunnels()` to filter by user, support `--all-users`
- [ ] Update D-Bus interface: methods now include `username` parameter or filter
- [ ] Test: Alice creates tunnels, Bob lists only his, admin lists all

### Phase 4: CLI Enhancements (Week 7)

- [ ] Add `--adapter` option to `tunnel create`
- [ ] Add `--session` option to all tunnel commands
- [ ] Add `--all-users` flag to `tunnel list`
- [ ] Add `tunnel login`, `tunnel logout`, `tunnel sessions` commands
- [ ] Update help text and man pages
- [ ] Shell completion for session names

### Phase 5: Testing & Polish (Week 8-10)

- [ ] Integration tests: multi-user scenario
- [ ] Security audit: session isolation, encryption
- [ ] Performance: many sessions (10+) active simultaneously
- [ ] Documentation: multi-user guide, session management
- [ ] Bug fixes

---

## 13. Open Questions

1. **Can a single Proton account have multiple simultaneous sessions?**
   - Yes, Proton allows ~10 concurrent devices. Each session is a "device".
   - So alice_work and alice_personal can both be active (same account, different session names)

2. **WireGuard adapter session management**:
   - WireGuard doesn't have "sessions" - just config file
   - Our "session" for WireGuard is just a named reference to a config file
   - Simple: session_name → config_file path

3. **Session expiration handling**:
   - Proton sessions expire (access token 1h, refresh token 30d)
   - Need background refresh or on-demand refresh when connecting
   - If refresh fails, mark session as invalid, user must re-login

4. **Multi-user D-Bus authentication**:
   - Currently D-Bus service is system-wide
   - Any user can connect to it via D-Bus (but Polkit restricts actions)
   - Polkit should enforce:
     - Can only create tunnels for self unless admin
     - Can only manage own sessions unless admin

---

## 14. Conclusion

This enhanced design enables:

✅ **Multiple Proton users** on same system (alice, bob, charlie)
✅ **Multiple sessions per user** (alice_work, alice_personal)
✅ **Multiple VPN backends** (Proton, Psiphon, WireGuard, ...)
✅ **Per-user tunnel isolation** (namespaces)
✅ **Shared sessions** (admin can create tunnel using any session)
✅ **Backward compatibility** (default session works)

**Total estimated additional work**: 4-6 weeks on top of base multi-tunnel.

---

**Ready to implement?** I can start building the `SessionManager`, storage backends, and modified adapters.
