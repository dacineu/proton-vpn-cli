# Phase 4: Polish, Security & Compatibility - Research

**Researched:** 2025-03-21
**Domain:** Security hardening, backward compatibility, integration testing, TOTP encryption, credential sanitation
**Confidence:** HIGH

## Summary

Phase 4 finalizes v1.0 by hardening security (socket perms, SO_PEERCRED, credential sanitation), ensuring backward compatibility via D-Bus forwarding, completing integration tests, and consolidating documentation. Builds on Phases 1-3 patterns.

**Primary recommendation:** Implement as opt-in via `--totp=off` default; use existing patterns from resource_allocator.py and dummy adapter CLI.

<user_constraints>
## User Constraints (from CONTEXT.md)

### Locked Decisions

**TOTP Security Layer (Dynamic Configuration)**
- MTM daemon flag: `--totp=on|off` (default: `off`)
- TOTP disabled when external PGP service unreachable (auto-fail safe)
- System operates without TOTP when disabled/unreachable (no warnings)
- This allows intranet-only deployments or admin opt-out

**TOTP Encryption Model**
- All data flows encrypted/decrypted using current TOTP value as symmetric key
  - CLI → MTM (D-Bus)
  - MTM ↔ Adapter (control channel)
  - CLI ↔ Adapter (tunnel operations)
- Key derivation: Use TOTP directly (no HKDF) — 6-digit code converted to bytes, zero-padded to 16/32 bytes
- TOTP secrets **not stored** in MTM: downloaded from external PGP service on-demand, kept in memory transiently
- If external service unreachable, fall back to unencrypted mode

**Legacy D-Bus API Forwarding**
- Legacy D-Bus methods (`CreateTunnel`, `ConnectTunnel`, `DisconnectTunnel`, `DestroyTunnel`, `ListTunnels`, `GetTunnelStatus`) preserved
- Implementation forwards internally:
  1. Legacy call arrives at D-Bus service
  2. If adapter not running, call `StartAdapter` (with session token handling)
  3. Forward request to adapter via control socket (transparent)
- Legacy API respects `--totp` flag:
  - `--totp=on`: Legacy calls must include session token (same as new API)
  - `--totp=off`: Legacy calls accepted without session token (backward compatible)
- No deprecation warnings in this release

**Socket Permissions & Authenticity**
- Adapter CLI sockets: `0600`, owned by the user who started the adapter
- Control socket (MTM ↔ Adapter): `0660` to allow MTM (root) and adapter (user) group access
- `SO_PEERCRED` used on control socket to verify connecting process is a child of MTM (PID matches registry entry)
- Adapter CLI socket permissions verified in integration test (manual check in TST-01)

**Test Strategy (Phase 4)**
- Create **empty test stubs** for all integration tests (TST-01, TST-02, TST-03)
- Stubs include test function signatures and basic assertions; implementation deferred
- Full test implementation occurs after all phases complete (final verification stage)

**Documentation Organization**
- **Single primary architecture document** in `docs/` root
- **Dual documentation tree**:
  - `docs/user/` — End-user facing: architecture overview, migration guide, usage concepts
  - `docs/developer/` — Developer facing: implementation details, adapter guide, protocol specs, testing strategies
- `docs/INDEX.md` acts as navigation hub
- Migration guide (DOC-02) placed in `docs/developer/`
- Developer adapter implementation guide (DOC-03) either extracted from `ADAPTER_INTEGRATION.md` or referenced directly

**Keyring & PGP Service Integration**
- Use `keyring` Python package for keyring access
- External PGP service stores per-user TOTP secrets; MTM downloads on-demand during user session setup
- TOTP secrets remain only in transient memory; zeroized after use or on shutdown
- Plan includes task to "harden keyring integration with external PGP service"
- No local persistence of TOTP secrets; if external service unavailable, TOTP layer stays disabled

### Claude's Discretion

**Deferred Ideas**
- Full TOTP encryption implementation details (HKDF vs direct use)
- Runtime reconfiguration of `--totp` (hot-reload) — requires daemon restart
- External PGP service client fallback chain (multiple PGP servers)
- Advanced threat model: encrypt process memory against swap, use `mlock`
- CLI subcommand to manually refresh TOTP secret from PGP service

</user_constraints>

<phase_requirements>
## Phase Requirements

| ID | Description | Research Support |
|----|-------------|-----------------|
| COMP-01 | Legacy D-Bus methods continue to work by forwarding to adapter | Section "Backward Compatibility Strategy" |
| COMP-02 | Old and new APIs can coexist | Section "Backward Compatibility Strategy" (TOTP flag handling) |
| SEC-01 | Socket permissions: CLI socket `0600` | Section "Unix Socket Security Hardening" |
| SEC-02 | Credentials via stdin not visible in `/proc`; buffer cleared | Section "Credential Sanitation Patterns" |
| SEC-03 | Control socket verifies peer via `SO_PEERCRED` | Existing `resource_allocator.py` + Section 1 |
| TST-01 | Full e2e flow integration test | Section "Integration Testing Plan" + Validation table |
| TST-02 | Crash recovery verifies namespace cleanup | Section "Integration Testing Plan" (crash simulation) |
| TST-03 | Concurrent connection test verifies isolation | Section "Integration Testing Plan" (asyncio.gather) |
| DOC-01 | Architecture documentation updated | Section "Documentation Structure" (ARCHITECTURE.md) |
| DOC-02 | Migration guide | Existing docs/developer/MIGRATION.md (verify) |
| DOC-03 | Developer adapter guide | Existing docs/developer/ADAPTER_IMPLEMENTATION_GUIDE.md |

</phase_requirements>

## Standard Stack

### Core
| Library | Version | Purpose | Why Standard |
|---------|---------|---------|--------------|
| Python | 3.9+ | Runtime | Project target |
| asyncio | stdlib | Async I/O | All components built on async |
| pydantic | 2.x | Data validation | Config models (ConnectionConfig, Tunnel) |
| dbus-next | 0.2.x | D-Bus communication | Modern async D-Bus |
| pyroute2 | 0.7+ | Network namespace & routing | Linux network configuration |

### Supporting
| Library | Version | Purpose | When to Use |
|---------|---------|---------|-------------|
| keyring | 25.x | System keyring access | External PGP service integration |
| cryptography | 43.x | Cryptographic operations | Optional for TOTP secret memory protection |
| pyotp | 2.9.x | TOTP generation/verification | Verify 6-digit codes against secret |

### Alternatives Considered
| Instead of | Could Use | Tradeoff |
|-----------|-----------|----------|
| keyring | Direct libsecret calls | keyring cross-platform; direct calls Linux-only |
| pyroute2 | `ip` command subprocess | pyroute2 pure Python; no shell injection risk |
| dbus-next | dbus-python | dbus-next async-compatible, actively maintained |

**Installation:** `pip install -e ".[development]"`

---

## Architecture Patterns

### Recommended Project Structure
```
multi-tunnel-namespace/src/
├── daemon/
│   ├── daemon.py          # VPNDaemon: main orchestrator
│   ├── adapter_registry.py # Tracks adapter processes by PID
│   └── resource_allocator.py # Internal socket server, SO_PEERCRED auth
├── libvpnmanager/
│   ├── adapters/base.py   # VPNAdapter abstract class
│   ├── ipc/unix_socket.py # UnixSocketServer/Client
│   ├── dbus/service.py    # D-Bus service with legacy methods
│   ├── sessions/manager.py # SessionManager (to be removed for TOTP)
│   ├── routing/namespace.py # NetworkNamespaceRouting
│   ├── models/            # Tunnel, config, exceptions
│   ├── client.py          # ManagerClient, AdapterClient
│   └── manager.py         # TunnelManager (standalone)
├── adapters/
│   ├── dummy_adapter/
│   │   ├── cli.py         # Dual-server, stdin credentials
│   │   └── adapter.py
│   └── proton_vpn_adapter/
├── cli/tunnel.py          # CLI commands
└── pyproject.toml
```

### Pattern 1: Dual-Server Adapter Architecture

**What:** Each adapter runs two concurrent servers:
1. CLI socket server (newline-delimited JSON) — accepts CLI connections
2. Control connection to MTM (length-prefixed JSON) — sends AllocateTunnel/ReleaseTunnel

**When:** Universal for all adapters.

**Example:** From `adapters/dummy_adapter/cli.py`:
```python
cli_server = await asyncio.start_unix_server(handle_cli, cli_socket_path)
os.chmod(cli_socket_path, 0o600)
control_reader, control_writer = await asyncio.open_unix_connection(MTM_CONTROL_SOCKET)
register = {'msg_type': 'register', 'session_id': session_id,
           'adapter_type': MTM_ADAPTER_TYPE, 'username': username,
           'session_token': session_token}
await send_control(control_writer, register)
```

### Pattern 2: SO_PEERCRED Authentication

**What:** Control socket uses Linux `SO_PEERCRED` to verify connecting process's PID/UID/GID.

**When:** All internal MTM↔adapter control connections.

**Example:** From `daemon/resource_allocator.py`:
```python
sock = writer.get_extra_info('socket')
cred = sock.getsockopt(socket.SOL_SOCKET, socket.SO_PEERCRED, 12)
pid, uid, gid = struct.unpack('3i', cred)
adapter = self._adapter_registry.get_by_pid(pid)
if adapter is None:
    writer.close(); return
```

### Pattern 3: Legacy D-Bus Method Forwarding

**What:** Legacy API methods become thin wrappers that forward to adapter via AdapterClient.

**Example skeleton:**
```python
@method()
async def CreateTunnel(self, config_dict, username):
    config = {k: v.value for k, v in config_dict.items()}
    conn_cfg = ConnectionConfig.from_dict(config)
    session_token = config.get('session_token') if self.manager.totp_enabled else None
    endpoint = await self.manager.ensure_adapter(
        adapter_type=config['adapter'], username=username,
        session_token=session_token)
    async with AdapterClient(endpoint, session_token=session_token) as client:
        tunnel = await client.create_tunnel(config['tunnel_name'], conn_cfg)
        return {k: _to_variant(v) for k, v in tunnel.to_dict().items()}
```

### Anti-Patterns
- Direct tunnel creation in D-Bus without adapter (breaks isolation)
- Storing TOTP secrets on disk
- Using `subprocess` for allocation (use async I/O)
- Global mutable state without `asyncio.Lock()`

---

## Don't Hand-Roll

| Problem | Don't Build | Use Instead | Why |
|---------|-------------|-------------|-----|
| TOTP generation/verification | Custom TOTP algorithm | `pyotp` library | RFC 6238, timing attack safe |
| Keyring integration | Direct libsecret calls | `keyring` package | Cross-platform abstraction |
| Network namespace ops | Shell to `ip netns` | `pyroute2` library | Pure Python, no shell injection |
| Unix socket framing | Ad-hoc framing | 4-byte big-endian length prefix | Consistent with existing code |
| Concurrent connections | Custom thread pools | `asyncio.Lock()` | Already in dummy adapter |
| Socket permission setting | `chmod` after bind | Temporary umask during bind | Race condition prevention |

**Key insight:** Phase 4 is polish and security; build on existing patterns. The TOTP "encryption" uses the 6-digit code directly as symmetric key — acceptable because Unix socket already protects against remote attackers; TOTP provides authentication, not crypto-grade secrecy.

---

## Common Pitfalls

### Pitfall 1: Socket Permission Race Conditions

**What:** Socket visible with default umask permissions briefly.

**How:** Set umask before bind:
```python
sock = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
old_umask = os.umask(0o077)
try:
    sock.bind(path)
finally:
    os.umask(old_umask)
sock.listen(128)
```

### Pitfall 2: Credentials in `/proc/<pid>/environ`

**What:** Environment variables expose credentials to any process reading `/proc`.

**How:** Use stdin exclusively; never pass credentials via environment. Daemon `_spawn_adapter` writes to `proc.stdin`.

### Pitfall 3: Insecure Memory Zeroing

**What:** Immutable `bytes`/`str` cannot be zeroed; original data persists.

**How:** Use `bytearray` for mutable buffers:
```python
buf = bytearray(secret_bytes)
# ... use buf ...
for i in range(len(buf)):
    buf[i] = 0
```
Or `ctypes.memset(ctypes.addressof(ctypes.c_char.from_buffer(buf)), 0, len(buf))`.

### Pitfall 4: SO_PEERCRED Partial Authentication

**What:** Accepting any UID or not checking that PID matches a registered adapter.

**How:** Always look up adapter in registry via `get_by_pid(pid)`; reject unknown. Also validate session token per request.

### Pitfall 5: TOTP Key Derivation Weakness

**What:** 6-digit numeric TOTP gives only ~20 bits entropy.

**Why acceptable:** Threat model assumes local IPC already protected by Unix socket perms and `SO_PEERCRED`. TOTP provides authentication, not encryption against offline attack. Document this limitation.

### Pitfall 6: Legacy API Incompatibility

**What:** Legacy callers break when `--totp=on` because they lack `session_token`.

**How:** Honor `--totp` flag:
- `off`: accept calls without token
- `on`: require token; return error `NEED_SESSION` if missing (caller should call `Verify2FA`)

---

## Code Examples

### Adapter CLI Socket with Permissions
```python
cli_socket_path = f"/run/mtm/adapters/{username}_{MTM_ADAPTER_TYPE}.sock"
Path(cli_socket_path).parent.mkdir(parents=True, exist_ok=True)
try:
    Path(cli_socket_path).unlink(missing_ok=True)
except Exception as e:
    logger.warning(f"Could not remove stale socket: {e}")
cli_server = await asyncio.start_unix_server(handle_cli, cli_socket_path)
try:
    os.chmod(cli_socket_path, 0o600)
except Exception as e:
    logger.warning(f"Could not set socket permissions: {e}")
```
Source: `adapters/dummy_adapter/cli.py` lines 295-313

### Credential Input via Stdin
```python
stdin_reader = asyncio.get_reader()
startup_bytes = await stdin_reader.readuntil(b'\n')
for i in range(len(startup_bytes)):
    startup_bytes[i] = 0
startup_str = startup_bytes.decode().strip()
data = json.loads(startup_str)
vpn_creds = data.get('vpn_credentials', {})
vpn_creds.clear()
totp_secret = None  # drop reference
```
Source: `adapters/dummy_adapter/cli.py` lines 259-270, 344-350

### Control Socket SO_PEERCRED Auth
```python
sock = writer.get_extra_info('socket')
cred = sock.getsockopt(socket.SOL_SOCKET, socket.SO_PEERCRED, 12)
pid, uid, gid = struct.unpack('3i', cred)
adapter = self._adapter_registry.get_by_pid(pid)
if adapter is None:
    writer.close(); return
self._authenticated.add(writer)
```
Source: `daemon/resource_allocator.py` lines 63-91

### Testing Socket Permissions
```python
import stat
from pathlib import Path
socket_path = endpoint.replace('unix://', '')
mode = stat.S_IMODE(Path(socket_path).stat().st_mode)
assert mode == 0o600
```
Source: `tests/integration/test_phase1_foundation.py` lines 36-40

---

## State of the Art

| Old Approach | Current Approach | When Changed | Impact |
|--------------|------------------|--------------|--------|
| Session persistence on disk | In-memory only; adapter holds credentials | Phase 4 | No credential files; requires login after restart |
| In-process adapter | Separate adapter processes with IPC | Phase 1-2 | Crash isolation, multi-tunnel |
| Single socket | Dual-socket (CLI + control) | Phase 1 | Clear separation; control channel authenticated |
| No TOTP | Optional TOTP encryption on all channels | Phase 4 (plan) | Per-request 2FA; defense-in-depth for local IPC |
| Direct D-Bus ops | D-Bus forwarding to adapter | Phase 4 (plan) | Legacy API compatibility while using new architecture |

**Deprecated:**
- `protonvpn session` commands → replaced by `protonvpn adapter`
- `~/.local/share/protonvpn/sessions/` storage → no longer used
- In-process adapter modules in daemon → standalone adapters

---

## Open Questions

1. **TOTP secret rotation**: If user resets 2FA while adapter running, validation fails. Should we hot-reload? Deferred: restart required.

2. **External PGP service client design**:
   - Config: env var `PROTONVPN_PGP_SERVICE_URL`?
   - Authentication to service? Possibly use user's existing session or system-wide trusted.
   - Caching: brief in-memory cache (TTL ~30s) to avoid fetch on every spawn.
   - Error handling: network failure → fallback to TOTP=off silently.

3. **Session token lifetime**: Not documented; assume tied to daemon lifetime or fixed duration (1h?). Need to verify.

4. **Legacy auto-start credentials**: When legacy `CreateTunnel` triggers adapter auto-start, what credentials to use? Legacy method may accept `username` and `password` parameters? Need to check exact D-Bus signature from DBUS_SECURITY_AND_ARCHITECTURE.md.

5. **Testing `/proc/<pid>/environ` leakage**: Automation: spawn adapter, read its `/proc/self/environ` (if same user) or use `ps e` to inspect. Could be flaky; may need manual verification or use of `ptrace` (requires root).

---

## Validation Architecture

> Config: `.planning/config.json` has `workflow.nyquist_validation = true` (default)

### Test Framework
| Property | Value |
|----------|-------|
| Framework | pytest with `pytest-asyncio` |
| Config file | `multi-tunnel-namespace/pytest.ini` |
| Quick run | `pytest tests/unit -x` |
| Full suite | `sudo pytest tests/integration -x` |

### Requirements → Test Map

| Req ID | Behavior | Test Type | Automated Command | Status |
|--------|----------|-----------|-------------------|--------|
| COMP-01 | Legacy `CreateTunnel` forwards to adapter | integration | `pytest tests/integration/test_phase4_legacy_forwarding.py::test_create_tunnel_uses_adapter -x` | ❌ Stub needed |
| COMP-02 | TOTP=off accepts legacy calls w/o token | integration | `pytest tests/integration/test_phase4_legacy_forwarding.py::test_legacy_without_totp_token -x` | ❌ Stub |
| SEC-01 | Socket mode = 0600 | integration | `pytest tests/integration/test_phase4_security.py::test_adapter_socket_mode -x` | ❌ Stub |
| SEC-02 | No credentials in `/proc/<pid>/environ`; buffers zeroed | integration | `pytest tests/integration/test_phase4_security.py::test_credential_leakage -x` | ❌ Stub |
| SEC-03 | Control socket rejects different UID | integration | `pytest tests/integration/test_phase4_security.py::test_control_socket_peercred -x` | ❌ Stub |
| TST-01 | Full e2e flow | integration | `pytest tests/integration/test_phase4_e2e.py::test_full_flow -x` | ❌ Stub |
| TST-02 | Crash recovery cleans namespace | integration | `pytest tests/integration/test_phase3_crash_recovery.py::test_adapter_crash_cleans_namespace -x` | ✅ Existing (adapt for TST-02) |
| TST-03 | Concurrent create_tunnel from multiple clients | integration | `pytest tests/integration/test_phase4_concurrency.py::test_concurrent_tunnel_creation -x` | ✅ Existing pattern (need stub) |
| DOC-01 | Architecture doc exists with required sections | manual | Verify `docs/ARCHITECTURE.md` contains Adapter Lifecycle, Dual-Channel Communication | ⚠️ Needs creation |
| DOC-02 | Migration guide in `docs/developer/` | manual | Check `docs/developer/MIGRATION.md` exists | ✅ Present |
| DOC-03 | Developer adapter guide | manual | Check `docs/developer/ADAPTER_IMPLEMENTATION_GUIDE.md` exists | ✅ Present |

### Wave 0 Gaps (stub files to create)
- [ ] `tests/integration/test_phase4_security.py` — SEC-01, SEC-02, SEC-03
- [ ] `tests/integration/test_phase4_legacy_forwarding.py` — COMP-01, COMP-02
- [ ] `tests/integration/test_phase4_e2e.py` — TST-01
- [ ] `tests/integration/test_phase4_concurrency.py` — TST-03 (multi-process)
- [ ] `docs/ARCHITECTURE.md` — merger of existing design docs with sections: Overview, Components, Data Flow, Adapter Lifecycle, Dual-Channel Communication, Security Model, Extension Points

**Stub template:**
```python
@pytest.mark.asyncio
async def test_adapter_socket_mode(manager_client, dummy_credentials):
    """SEC-01: Adapter CLI socket created with mode 0600."""
    raise NotImplementedError("Stub for SEC-01")
```

---

## Sources

### Primary (HIGH)
- `src/daemon/resource_allocator.py` — SO_PEERCRED, namespace allocation
- `src/adapters/dummy_adapter/cli.py` — dual-server, stdin credentials
- `src/libvpnmanager/ipc/unix_socket.py` — socket server with perms
- `src/libvpnmanager/dbus/service.py` — D-Bus legacy methods
- `tests/integration/conftest.py` — fixtures (daemon, manager_client)
- `tests/integration/test_phase1_foundation.py` — socket perm checks, token validation
- `tests/integration/test_phase3_crash_recovery.py` — crash simulation
- `.planning/REQUIREMENTS.md` — Phase 4 reqs
- `04-CONTEXT.md` — locked decisions

### Secondary (MEDIUM)
- Python `socket` module docs — `SO_PEERCRED` (stdlib)
- `pyroute2` docs — network namespaces
- `keyring` docs — cross-platform keyring
- `pytest-asyncio` — async test patterns

### Tertiary (LOW — verify later)
- TOTP key derivation: direct use of 6-digit code (design trade-off, not formal audit)
- External PGP service protocol (unspecified)
- `pyotp` API specifics (assumed standard)

---

**Metadata**
- Confidence: HIGH — derived from existing implementation and established best practices
- Valid until: 60 days (stable stack)
- Research date: 2025-03-21

## RESEARCH COMPLETE ✓

Summary:
- Unix socket security: umask for 0600/0660; SO_PEERCRED already in resource_allocator.py
- Backward compatibility: Legacy D-Bus methods forward to AdapterClient; respect `--totp` flag
- Integration testing: use existing fixtures; create stubs for SEC-*, COMP-*
- TOTP encryption: use pyotp; 6-digit code as key acceptable for local IPC threat model
- Credential sanitation: bytearray buffers, zero after use, stdin only
- Legacy D-Bus: forwarding with session token propagation and error translation
- Documentation: existing structure good; need ARCHITECTURE.md merger
- Validation: 11 tests mapped; 4 stub files to create + architecture doc

Next step: /gsd:plan-phase 4 (using this research)
