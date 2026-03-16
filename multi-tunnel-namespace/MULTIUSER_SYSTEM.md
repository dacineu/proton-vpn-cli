# Multi-User, Multi-Backend Tunnel System

**Enhanced Architecture** for `libvpnmanager`

---

## Overview

The system now supports:

### ✅ Multiple Concurrent Users
- Alice can have tunnels using her Proton account
- Bob can have tunnels using his Proton account (or Psiphon, WireGuard)
- Each user's tunnels are isolated and owned by that user
- Admins can view/manage all users' tunnels

### ✅ Multiple VPN Backends
- **Proton VPN**: OAuth sessions, multiple accounts
- **Psiphon**: Config-based connections
- **WireGuard**: Static config files
- Pluggable: add new adapters easily

### ✅ Session Management
- Sessions are named (e.g., "work", "personal", "gaming")
- Each session stores credentials/config separately
- Sessions persist across daemon restarts (encrypted storage)
- Session login/logout commands

---

## Architecture

### Data Model

```
Tunnel {
    name: "work"
    adapter: "proton"
    session_name: "alice_work"
    username: "alice"              # OS user who created this tunnel
    device: "proton0"
    namespace: "vpn_work"
    endpoint: "us-proton.example.com"
    ...
}

Session {
    adapter: "proton"
    session_name: "alice_work"
    username: "alice"
    access_token: "..."
    refresh_token: "..."
    expires_at: datetime
    ...
}
```

### Components

1. **SessionManager**
   - Stores/loads sessions from `$XDG_DATA_HOME/protonvpn/sessions/`
   - Validates sessions (expiry, config existence)
   - Provides `get_connector(adapter, session_name, username) → MultiTunnelVPNConnector`

2. **TunnelManager** (enhanced)
   - Accepts `username` parameter on all tunnel operations
   - Checks ownership/permissions
   - Creates adapters on-demand per session
   - Multi-user aware: `list_tunnels(username, all_users)`

3. **Adapters** (Proton, Psiphon, WireGuard)
   - Now accept `Session` object in constructor
   - Use that session's credentials to connect
   - Support multi-tunnel per session (same Proton account → multiple tunnels)

4. **D-Bus Service**
   - All methods require `username` parameter
   - New methods: `ListSessions`, `Login`, `Logout`
   - Permissions: Polkit rules enforce user rights

5. **CLI**
   - `protonvpn tunnel create ... --adapter proton --session work`
   - `protonvpn tunnel sessions` (list available sessions)
   - `protonvpn tunnel login --adapter proton --session work --username alice@protonmail.com`
   - `protonvpn tunnel logout --session work`
   - `--all-users` flag for admins

---

## Session Storage

### Directory Layout

```
$HOME/.local/share/protonvpn/sessions/
├── proton/
│   ├── alice_work.json          # Encrypted (future)
│   ├── alice_personal.json
│   └── bob_work.json
├── psiphon/
│   ├── bob_psiphon.json
│   └── alice_psiphon.json
└── wireguard/
    ├── bob_wg.conf              # WireGuard config file
    └── alice_wg.conf
```

### Proton Session JSON

```json
{
  "adapter": "proton",
  "session_name": "alice_work",
  "username": "alice",
  "access_token": "eyJhbG...",
  "refresh_token": "eyJhbG...",
  "expires_at": "2026-03-16T12:00:00Z",
  "cookies": {"session": "abc123"},
  "created_at": "2026-03-15T10:00:00Z"
}
```

**Note**: Currently stored in plain JSON. Should be encrypted with user's keyring.

---

## CLI Usage Examples

### First-Time Setup

```bash
# Alice logs in with her Proton account, creates a session called "work"
$ protonvpn tunnel login --adapter proton --session work --username alice@protonmail.com
Password: ********
2FA code: 123456
✓ Session 'work' created successfully

# Alice creates a tunnel using that session
$ protonvpn tunnel create us-tunnel --adapter proton --session work --country US
Creating tunnel 'us-tunnel' (adapter=proton, session=work)...
✓ Tunnel 'us-tunnel' created and connected
  Adapter: proton
  Session: work
  Device: proton0
  Namespace: vpn_us-tunnel
  Endpoint: us-proton.example.com

# Alice runs Firefox in that tunnel
$ protonvpn tunnel switch us-tunnel
Switching to namespace 'vpn_us-tunnel'...
[Now in namespace; all apps use US exit]
$ firefox &
exit  # back to default namespace

# Alice creates second tunnel with same session but different country
$ protonvpn tunnel create jp-tunnel --adapter proton --session work --country JP
Creating tunnel 'jp-tunnel'...
✓ Tunnel 'jp-tunnel' created and connected
  Adapter: proton
  Session: work
  Device: proton1
  Namespace: vpn_jp-tunnel

# Both tunnels active simultaneously!
```

### Multiple Users on Same Machine

```bash
# Bob logs in on same machine (different OS user, or same user with different session)
$ protonvpn tunnel login --adapter proton --session personal --username bob@example.com
Password: *****
✓ Session 'personal' created

$ protonvpn tunnel create de-tunnel --adapter proton --session personal --country DE
Creating tunnel 'de-tunnel'...
✓ Tunnel 'de-tunnel' created and connected

# List all tunnels (admin can see all users)
$ protonvpn tunnel list
NAME        ADAPTER    SESSION       OWNER   STATUS   ENDPOINT
us-tunnel   proton     work          alice   connected us-proton.example.com
jp-tunnel   proton     work          alice   connected jp-proton.example.com
de-tunnel   proton     personal      bob     connected de-proton.example.com

# Bob can only see his own tunnels unless admin
$ protonvpn tunnel list --username bob
NAME        ADAPTER    SESSION       OWNER   STATUS   ENDPOINT
de-tunnel   proton     personal      bob     connected de-proton.example.com

# Switch to Bob's tunnel
$ protonvpn tunnel switch de-tunnel
[Now in Bob's Germany tunnel]
```

### Using Different Backends

```bash
# Bob also wants a Psiphon tunnel
$ protonvpn tunnel login --adapter psiphon --session bob_psiphon --username bob
# (Psiphon might not need password if using config)
✓ Session created

$ protonvpn tunnel create psiphon-tunnel --adapter psiphon \
    --session bob_psiphon \
    --entry-country US \
    --exit-country DE
Creating tunnel 'psiphon-tunnel'...
✓ Tunnel 'psiphon-tunnel' created

# WireGuard (static config)
$ protonvpn tunnel create wg-tunnel --adapter wireguard \
    --session bob_wg \
    --config /home/bob/wireguard/work.conf
Creating tunnel 'wg-tunnel'...
✓ Tunnel 'wg-tunnel' created

# List all sessions
$ protonvpn tunnel sessions
ADAPTER    SESSION           OWNER   STATUS   DETAILS
proton     work              alice   active   exp:2026-03-23
proton     personal          bob     active   exp:2026-03-20
psiphon    bob_psiphon       bob     active
wireguard  bob_wg            bob     active   config:work.conf
```

---

## Permissions Model

### Ownership

- When a user creates a tunnel, that tunnel belongs to them (`tunnel.username = creator`)
- Users can only manage (list, connect, disconnect, destroy) their own tunnels
- **Admins** (members of `sudo`/`wheel` group) can manage all tunnels:
  - `protonvpn tunnel list --all-users`
  - `protonvpn tunnel destroy <name> --username <target_user>`

### Session Access

- Users can only use sessions that they created
- However, **sessions are not per-tunnel but per-account**:
  - Alice creates session "work" (her Proton account)
  - Alice can create multiple tunnels using that same "work" session (US, UK, CA, etc.)
  - All those tunnels share the same underlying Proton credentials
  - They are rate-limited by Proton's device limit (usually ~10)

### Cross-User Tunnel Usage?

**Design decision**: A user can create a tunnel using a session that belongs to another user, if they know the session name? For security, sessions should be scoped to the user who created them. The SessionManager enforces that when loading a session, the `username` must match the session's `username` OR the requester is admin.

**Example**:
- Alice created session "alice_work" (owned by alice)
- Bob cannot create a tunnel using session "alice_work" because he's not alice
- Admin could, by specifying `--username alice`

---

## Technical Details

### SessionManager

Key methods:

```python
async def load_session(adapter, session_name, username, password=None) -> Session
    # Load existing session or create new via login

async def get_connector(adapter, session_name, username) -> MultiTunnelVPNConnector
    # Returns connector configured with that session's credentials

async def list_sessions(adapter=None, username=None) -> List[SessionInfo]
    # Scan storage and return session summaries

async def logout(adapter, session_name, username) -> bool
    # Revoke and delete session

async def cleanup_user_sessions(username)
    # Called on user logout to clean up all their sessions
```

### MultiTunnelVPNConnector

Each `(adapter, session_name)` pair gets its own connector instance stored in `SessionManager._connectors`. The connector manages multiple tunnels **using the same credentials**.

Example:

```python
# Load connector for Alice's "work" session
connector = await session_manager.get_connector("proton", "work", "alice")

# Create first tunnel (US)
conn1 = await connector.connect("us-tunnel", server_us, "wireguard")
# Uses Alice's session tokens

# Create second tunnel (JP) with same session
conn2 = await connector.connect("jp-tunnel", server_jp, "wireguard")
# Same tokens, different tunnel

# Both tunnels active, both use Alice's account (count as 2 devices)
```

### TunnelManager

Now takes `username` on all tunnel operations:

```python
async def create_tunnel(config: ConnectionConfig, username: str) -> Tunnel
async def connect_tunnel(tunnel_name: str, username: str) -> Tunnel
async def disconnect_tunnel(tunnel_name: str, username: str) -> None
async def destroy_tunnel(tunnel_name: str, username: str) -> None
async def list_tunnels(username: Optional[str], all_users: bool) -> List[Tunnel]
async def get_tunnel(tunnel_name: str, username: str) -> Optional[Tunnel]
```

### D-Bus Interface (org.protonvpn.Manager)

All methods now include `username`:

- `CreateTunnel(config_dict: a{sv}, username: s) → a{sv}`
- `ConnectTunnel(name: s, username: s) → b`
- `DisconnectTunnel(name: s, username: s) → b`
- `DestroyTunnel(name: s, username: s) → b`
- `ListTunnels(username: s, all_users: b) → aa{sv}`
- `GetTunnelStatus(name: s, username: s) → a{sv}`
- `GetTrafficStats(name: s, username: s) → (tt)`
- `ListSessions(username: s, adapter: s, all_users: b) → aa{sv}` (new)
- `Login(adapter: s, session_name: s, username: s, password: s, twofa: s) → a{sv}` (new)
- `Logout(adapter: s, session_name: s, username: s) → b` (new)

---

## Security Considerations

### Session Storage Encryption

**Current**: Sessions stored as JSON (plain text). **Not secure**.

**Required**: Encrypt session files with user's login keyring:
- Use `proton-keyring-linux` or Python `keyring` library
- Encrypt with user's login password or keyring master password
- Decrypt on load, keep in memory only
- Wipe from memory on logout/shutdown

### Polkit Rules

Daemon needs Polkit rules to enforce:
- Any user can create tunnels using their own sessions
- Only admins can list all users' tunnels (`--all-users`)
- Only admins can destroy others' tunnels

Example rule:

```javascript
polkit.addRule(function(action, subject) {
    if (action.id == "org.protonvpn.manager.create-tunnel" ||
        action.id == "org.protonvpn.manager.destroy-tunnel") {

        // Admins can do anything
        if (subject.user == "root") {
            return polkit.Result.YES;
        }

        // Check if tunnel belongs to user
        // TODO: Need to inspect arguments to verify ownership
        // But Polkit can't easily inspect D-Bus call arguments
        // Alternative: Let daemon do permission check, Polkit just allows operation
        // Return YES for authenticated users, daemon enforces ownership
        return polkit.Result.YES;
    }
});
```

Actually: D-Bus calls will include `username`. Daemon should check:
- If `username` matches the tunnel's owner OR
- If caller is admin (check Polkit)

Polkit can authorize the operation type, daemon enforces per-resource ownership.

### Session Expiry

- Proton sessions expire (access token 1h, refresh token 30d)
- On connection attempt, if session invalid, try refresh
- If refresh fails, mark session as expired, user must re-login
- Show clear error: "Session expired, please run: protonvpn tunnel login ..."

---

## Backward Compatibility

### Old Single-User Model

Previous `protonvpn connect` command assumed:
- Single user (whoever ran it)
- Single session (implicit "default")
- Single adapter (Proton only)

**Compatibility mode**:

```bash
# Old command (still works):
$ protonvpn connect --country US
# Equivalent to:
$ protonvpn tunnel create default --adapter proton --session default --country US
# Assuming user is logged in (session "default" for current user)
```

To support this:
1. On first `protonvpn connect`, automatically create a "default" session for the user (by logging in interactively)
2. Store that session as `~/.local/share/protonvpn/sessions/proton/<user>_default.json`
3. Then `protonvpn connect` uses that session

Alternatively, deprecate old command and migrate to new tunnel commands.

---

## Implementation Status

### ✅ Complete

- SessionManager with load/save/list/logout
- Base Session classes (ProtonSession, PsiphonSession, WireGuardSession)
- Enhanced TunnelManager with username tracking and permissions
- Permissions: admins via `_is_admin()` (group check)
- D-Bus service updates: all methods have username
- New D-Bus methods: ListSessions, Login, Logout
- D-Bus client updates: pass username everywhere
- CLI commands: fully multi-user aware

### 🔴 Incomplete (Needs Proton API)

- `ProtonSession.create_from_login()` actual implementation (needs proton-vpn-api-core)
- `ProtonSession.refresh()` (needs refresh endpoint)
- Session encryption (should encrypt at rest with keyring)
- Polkit rules (need to write)

### 🟡 Partial

- PsiphonAdapter, WireGuardAdapter (need to implement but straightforward)
- Error handling in CLI (some cases missing)
- Session auto-cleanup on user logout (systemd user stop?)

---

## Testing

### Unit Tests (to write)

```python
# Test SessionManager
- test_load_nonexistent_session_raises
- test_save_and_load_proton_session
- test_list_sessions_filters_by_user
- test_list_sessions_all_users_admin_only

# Test TunnelManager
- test_create_tunnel_assigns_ownership
- test_user_cannot_manage_others_tunnels
- test_admin_can_manage_all_tunnels

# Test D-Bus service
- test_create_tunnel_with_username
- test_list_tunnels_filters_by_user
- test_list_tunnels_all_users_requires_admin
```

### Integration Tests

```python
# Test multi-user scenario
- user_alice creates tunnel "work"
- user_bob creates tunnel "personal"
- alice lists tunnels → only sees "work"
- bob lists tunnels → only sees "personal"
- admin lists with --all-users → sees both

# Test multi-backend
- Create Proton tunnel, Psiphon tunnel, WireGuard tunnel simultaneously
- Verify they get different namespaces, devices
- Verify isolation between them
```

---

## Future Enhancements

1. **Session Auto-Logout**: When user logs out of OS session, daemon should clean up their tunnels & sessions
   - Systemd user service sends signal to daemon on logout
   - Or session manager monitors user login sessions via `loginctl`

2. **Session Sharing**: Allow users to share sessions (e.g., family sharing one Proton account)
   - Currently sessions are private to creator
   - Could add `--share-with USER` option

3. **Session Import/Export**: Export session as file to transfer to another machine
   - Encrypt with password
   - `protonvpn tunnel export-session --session work > work.session`
   - `protonvpn tunnel import-session work.session`

4. **Per-Adapter Login Flow**:
   - Proton: OAuth web flow? (currently password-based)
   - Psiphon: Generate config with API key
   - WireGuard: Just point to config file (no login)

5. **Session Renewal**: Background job to refresh expiring sessions automatically

6. **Quota Management**: Track how many tunnels per session (Proton limits to ~10). Reject creation beyond limit.

---

## Conclusion

The multi-user, multi-backend system provides:

- **Flexibility**: Multiple users, multiple accounts, multiple backends
- **Security**: Ownership enforcement, admin controls, per-user isolation
- **Usability**: Session management commands, per-user defaults
- **Extensibility**: New adapters just implement `Session` subclass and adapter class

**Next steps**:
1. Implement actual login for Proton (hook into proton-vpn-api-core)
2. Add session encryption with keyring
3. Write PsiphonAdapter and WireGuardAdapter
4. Write comprehensive tests
5. Update documentation and man pages

---

**Implementation Date**: 2026-03-16
**Status**: Core complete, needs Proton API integration
