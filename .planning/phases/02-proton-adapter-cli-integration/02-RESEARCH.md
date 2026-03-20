# Phase 2 Research: Proton Adapter & CLI Integration

**Date:** 2025-03-20
**Researcher:** Manual (API credit limitation)

---

## Domain Analysis

**Goal:** Migrate existing Proton VPN adapter from old architecture to new dual-socket pattern; integrate CLI tunnel commands to use direct adapter communication; implement credential prompt and adapter subcommands.

**Key Requirements:** ADPT-04, ADPT-05, CLI-03, CLI-04, CLI-05

---

## Existing Code Structure (Brownfield)

### Current Proton Adapter (Old Architecture)

**Location:** `src/adapters/proton_vpn_adapter/`

**Files:**
- `cli.py` — Entry point that runs as subprocess managed by daemon
- `adapter.py` — `ProtonVPNAdapter` class with session management, tunnel tracking
- `sessions/proton.py` — `ProtonSession` dataclass

**Current Pattern:**
```python
# cli.py (current)
async def main():
    session_json = os.getenv('MTM_SESSION_DATA')
    session = ProtonSession.from_dict(json.loads(session_json))
    adapter = ProtonVPNAdapter(session)
    control_socket = os.getenv('MTM_CONTROL_SOCKET')
    internal_socket = os.getenv('MTM_INTERNAL_SOCKET')
    server = UnixAdapterServer(adapter, control_socket, internal_socket)
    await server.run()
```

The adapter uses `UnixAdapterServer` (from `libvpnmanager.adapters.unix_adapter_server`) which likely implements an IPC protocol. It receives credentials via environment variable `MTM_SESSION_DATA` (JSON), not stdin.

**Important:** The adapter already has `_local_tunnels: Dict[str, Tunnel]` and `_connections: Dict[str, VPNConnection]` for multi-tunnel support. It tracks tunnels by name.

### Current CLI Tunnel Commands

**Location:** `src/cli/tunnel.py`

**Pattern:**
```python
client = ManagerClient()
await client.connect()
tunnel = await client.create_tunnel(config, username)
```

`ManagerClient.create_tunnel()` currently calls the old D-Bus `CreateTunnel` method on the daemon, which internally manages adapters in-process.

---

## Migration Strategy

### 1. Proton Adapter Migration (ADPT-04, ADPT-05)

**Objective:** Convert `proton_vpn_adapter/cli.py` to new dual-server pattern like dummy adapter.

**Changes needed:**

1. **Read credentials via stdin** (not `MTM_SESSION_DATA` env):
   ```python
   # New pattern (from dummy adapter)
   payload = json.loads(sys.stdin.read())
   session = ProtonSession.from_dict(payload['vpn_credentials'])
   session_token = payload.get('session_token')  # for CLI auth
   ```

2. **Dual-server architecture:**
   - Bind CLI Unix socket at `ADAPTER_ENDPOINT` env var
   - Connect to MTM control socket at `CONTROL_ENDPOINT` env var
   - Run both servers concurrently with `asyncio.gather()`

3. **Register handshake:**
   After control socket connects, send:
   ```json
   {"action": "register", "session_id": SESSION_ID, "adapter_type": "proton", "username": VPN_USERNAME}
   ```
   Receive response with expected `session_token` (if not already set via stdin).

4. **Session memory reuse:**
   The adapter already stores `self.session` and `self._connections`. Ensure:
   - Session is created once on startup from credentials
   - Multiple `CreateTunnel` calls reuse same `self.api` and `self.connector`
   - Connections stored in `self._connections` dict keyed by tunnel name

5. **Tunnel tracking:**
   Already present: `self._local_tunnels` dict. Ensure concurrent access protected by `asyncio.Lock`.

6. **CLI request handler:**
   - Accept NDJSON on CLI socket
   - Validate `session_token` on each request (from Phase 1 infrastructure)
   - Handle `CreateTunnel`, `DestroyTunnel`, `ListTunnels`, `GetStatus`
   - For `CreateTunnel`: call `self._ensure_api()`, then use multi-tunnel connector to create connection with tunnel_name

7. **Signal handling:**
   Graceful shutdown on SIGTERM/SIGINT, cleaning up all tunnels (call `DestroyTunnel` for each, then disconnect API).

**Implementation approach:**
- Start from `src/adapters/dummy_adapter/cli.py` as template
- Replace dummy tunnel creation with real Proton VPN connector calls
- Reuse `ProtonVPNAdapter` class methods from current implementation
- Preserve existing `UnixAdapterServer` logic if useful (but that's for D-Bus; new adapter uses raw NDJSON)

### 2. CLI Integration (CLI-03, CLI-04)

**Objective:** Update `cli/tunnel.py` to use new direct adapter flow; add `cli/adapter.py` for adapter management.

**Changes:**

1. **New flow in `tunnel create`:**

   ```python
   async def create_tunnel_via_adapter(config, username, credentials):
       # Step 1: Verify 2FA if needed (SEC-04/05)
       client = ManagerClient()
       await client.connect()
       try:
           totp_code = prompt_totp()  # interactive prompt
           session_token = await client.verify_2fa(totp_code)
       finally:
           await client.disconnect()

       # Step 2: Start or reuse adapter
       client = ManagerClient()
       await client.connect()
       try:
           adapter_info = await client.start_adapter(
               adapter_type=config.adapter,
               credentials=credentials,
               session_token=session_token  # pass token
           )
           endpoint = adapter_info['endpoint']
       finally:
           await client.disconnect()

       # Step 3: Connect to adapter directly and create tunnel
       adapter_client = AdapterClient(endpoint, session_token)
       await adapter_client.connect()
       try:
           tunnel = await adapter_client.create_tunnel(
               name=config.tunnel_name,
               config=config  # serialized appropriately
           )
           return tunnel
       finally:
           await adapter_client.disconnect()
   ```

2. **Credential prompt logic (CLI-04):**
   - Before starting adapter, need credentials (username/password for Proton)
   - Prompt only if adapter not already running for this user+type
   - Implementation: `ManagerClient.start_adapter()` will fail with specific error if credentials required, or we can check `ListAdapters()` first
   - Recommended: Attempt `start_adapter` with empty credentials; if adapter returns `requires_login`, prompt and retry

3. **Update existing `tunnel create` command:**
   - Replace old `client.create_tunnel(config, username)` call with new flow above
   - Handle credential gathering interactively (use `getpass.getpass()` for password)
   - Preserve existing output formatting

### 3. Adapter Subcommands (CLI-05)

**New file suggested:** `src/cli/adapter.py`

**Commands:**

```python
@click.group(name="adapter")
def adapter_group():
    """Manage adapter lifecycle."""

@adapter_group.command(name="list")
async def list_adapters():
    """List running adapters."""
    client = ManagerClient()
    await client.connect()
    try:
        adapters = await client.list_adapters()
        for a in adapters:
            click.echo(f"{a['type']}/{a['username']} → {a['endpoint']} (tunnels: {a['tunnel_count']})")
    finally:
        await client.disconnect()

@adapter_group.command(name="stop")
@click.argument("adapter_type", type=click.Choice(["proton", "psiphon", "wireguard", "dummy"]))
async def stop_adapter(adapter_type):
    """Stop adapter for current user."""
    client = ManagerClient()
    await client.connect()
    try:
        await client.stop_adapter(adapter_type)
        click.echo(f"Adapter '{adapter_type}' stopped.")
    finally:
        await client.disconnect()
```

**Registration:** Add `adapter_group` to main CLI entry point (likely `src/cli/main.py` or similar).

---

## Dependencies

- **Phase 1 complete:** ManagerClient.start_adapter(), AdapterClient, session token infrastructure, daemon StartAdapter D-Bus method.
- **Proton VPN API:** The adapter depends on `proton-vpn-api-core` with multi-tunnel support (already in requirements).
- **Daemon control socket handler:** Already implemented in Phase 1 (Register, token validation).

---

## Risks & Mitigations

| Risk | Impact | Mitigation |
|------|--------|------------|
| Proton VPN core library lacks multi-tunnel support | High — multiple concurrent connections may fail | Review `proton-vpn-api-core` integration; may need fork/patch as noted in adapter.py comments |
| Concurrent tunnel creation race conditions | Medium | Use asyncio.Lock in adapter (already present in dummy; adopt same pattern) |
| Credential prompt blocking in non-interactive environments | Medium | Allow credentials via env/args for scripting (out of scope for Phase 2? defer to later) |
| Adapter startup time (VPN login) causing CLI timeout | Medium | Consider async login with progress; but start_adapter already waits for socket bind only, not VPN login — so OK |
| Legacy D-Bus API compatibility | High | Phase 1 already preserved; Phase 2 must not break existing `client.create_tunnel()` callers |

---

## Open Questions (for discuss-phase if needed)

1. **AdHoc vs session-scoped credentials:** Should `start_adapter` accept full credentials (username/password) or just a reference to stored session? Currently design: credentials passed at start_adapter time.
2. **TOTP integration:** Phase 2 uses dummy tokens; real TOTP verification deferred to Phase 4. Should we still prompt for TOTP code now (with dummy validation) to validate flow? Or just pass dummy token?
3. **Error handling:** How should adapter signal `requires_login` to CLI? New error type? Or use existing `AuthenticationError`?
4. **Adapter stop behavior:** Should `stop_adapter` wait for adapter process to exit gracefully? Or fire-and-forget?

---

## Implementation Plan Outline

**Wave 1:** Migrate Proton adapter to dual-server pattern
- Refactor `adapters/proton_vpn_adapter/cli.py` to use new pattern (bind CLI socket, connect control, Register)
- Implement CLI request handler with session token validation
- Implement tunnel operations: CreateTunnel, DestroyTunnel, ListTunnels, GetStatus
- Ensure session reuse and concurrent connection safety

**Wave 2:** Update CLI tunnel commands
- Modify `cli/tunnel.py` create command to use start_adapter + AdapterClient flow
- Add credential prompt (username/password) only when adapter requires login
- Update legacy `create_tunnel` in ManagerClient to still work (forwarding) — already done in Phase 1?

**Wave 3:** Add adapter subcommands
- Create `cli/adapter.py` with list and stop commands
- Wire into main CLI
- Test end-to-end: adapter list shows running adapters; stop cleanly terminates

**Wave 4:** Integration tests
- Test Proton adapter startup (mocked)
- Test credential prompt logic
- Test direct tunnel creation flow
- Test adapter reuse (second tunnel skips credentials)
- Test concurrent tunnel creation

---

## References

- `src/adapters/dummy_adapter/cli.py` — reference implementation
- `src/adapters/dummy_adapter/adapter.py` — dummy adapter behavior
- `src/libvpnmanager/client.py` — ManagerClient and AdapterClient
- `src/daemon/daemon.py` — StartAdapter D-Bus method
- `docs/NEW_ADAPTER_ARCHITECTURE_SPECIFICATION.md` — original design spec
- `.planning/phases/01-foundation/1-CONTEXT.md` — Phase 1 implementation decisions

---

**Status:** Research complete — sufficient information to plan Phase 2.
