# Phase 1: Foundation — Adapter Lifecycle & Core Protocol - Context

**Gathered:** 2025-03-20
**Status:** Ready for planning

---

<domain>
## Phase Boundary

Establish the fundamental adapter process pattern with dual Unix sockets (CLI endpoint + control endpoint) and a working Dummy adapter that demonstrates the full flow: adapter startup, registration with MTM, namespace allocation control channel, and tunnel creation. No real VPN operations; focus on architecture and protocol.

---

</domain>

<decisions>
## Implementation Decisions

### Socket Paths and Naming

- Adapter CLI sockets: `/run/mtm/adapters/{username}_{adapter_type}.sock`
- Adapter control sockets: `/run/mtm/control/{username}_{adapter_type}.sock`
- MTM creates both directories at startup with `0755` root:root ownership
- Socket file mode: `0600`, owned by appropriate user (MTM sets this before spawning)

### Control Protocol

- Framing: NDJSON (newline-delimited JSON, one object per line)
- Pattern: All messages are request-reply; even notifications expect an ack response from MTM
- Error response format:
  ```json
  {
    "status": "error",
    "error": "Human-readable message",
    "code": "STRING_ERROR_CODE",
    "details": {}
  }
  ```
- String error codes: uppercase_with_underscores (e.g., `DEVICE_NOT_FOUND`, `INVALID_REQUEST`)
- Authentication: MTM verifies peer credentials via `SO_PEERCRED` on control socket connections; rejects mismatches between claimed username and actual UID
- No session tokens in Phase 1 (deferred to later for added security)

### Dummy Adapter Behavior

- Realistic simulation:
  - `CreateTunnel` returns varying device names (`dummy0`, `dummy1`, …) as tunnels are created
  - Implements full API: `CreateTunnel`, `DestroyTunnel`, `ListTunnels`, `GetStatus`
  - Allocates tunnel control channel: sends `AllocateTunnel` to MTM and waits for response (even if namespace creation is mocked)
  - 500ms–1s artificial delay to simulate VPN handshake latency
  - Tracks tunnels in `self.tunnels` dict like a real adapter
- Full lifecycle: `Register` on startup, `Shutdown` on exit, proper cleanup of `self.tunnels`

### Client Connection Pattern

- Default: connect on-demand — `AdapterClient` creates a new socket per operation, closes after response
- Optional persistent mode: `AdapterClient(persistent=True)` keeps long-lived connection for real-time features (traffic stats, signals) — usable if adapter supports it (Phase 2+)
- Async context manager supported: `async with AdapterClient(endpoint) as client:`
- Exceptions:
  - `AdapterConnectionError` — general I/O failure
  - `AdapterNotFound` — socket doesn't exist (adapter not running)
  - `AdapterCrashed` — connection broken, adapter died
- MTM handles crash cleanup independently via process monitoring; client errors don't affect MTM resource tracking

### Adapter Lifecycle Triggers

- `StartAdapter(adapter_type, credentials=None)`:
  - Derive session key from **VPN username** in credentials (not OS user)
  - Check `adapter_pool[(adapter_type, vpn_username)]` for alive adapter:
    - If alive → return existing endpoint
    - If dead → remove from pool, continue to spawn
  - Spawn new adapter process only when no alive adapter exists for that key
  - Generate ephemeral `session_id` (UUID) for tracking within MTM; passed to adapter via env
  - Block only until adapter CLI socket binds (use `wait_for_socket`, 10s timeout); do not wait for VPN login
  - If spawn fails (timeout, immediate crash) → raise `AdapterStartFailed`
- Credentials on subsequent calls:
  - If adapter already running for `(type, vpn_username)`, ignore any credentials supplied and return existing endpoint
  - To change credentials, user must `StopAdapter` first, then `StartAdapter` with new creds
- Multiple-session handling: Adapter internally manages protocol-specific limitations:
  - If protocol allows multiple connections from same account: adapter serves all tunnel requests on same global VPN session
  - If protocol allows only one connection: adapter may gracefully disconnect old session and re-login with new credentials when requested
- `StopAdapter(adapter_type, username=None)`:
  - If username omitted, use calling OS user's context to identify target adapter
  - MTM sends `Shutdown` on control socket; adapter exits gracefully; MTM cleans namespaces and removes from pool
- MTM ensures only one alive adapter per `(adapter_type, vpn_username)` at any time

### Error Handling Standards

- Logging:
  - Adapter and MTM log to stdout/stderr (unstructured for Phase 1; structured JSON later)
  - Levels: `INFO` (spawn, tunnel create, namespace ops), `WARNING` (recoverable issues), `ERROR` (failures that surface to user)
  - Include `session_id` and request correlation IDs where possible
- Control channel errors:
  - MTM logs protocol errors at WARNING level (invalid JSON, unknown action)
  - Transient errors (e.g., `ip netns add` fails with "File exists"): retry once after cleaning up stale namespace, then fail if persists
- User-facing errors:
  - CLI shows sanitized messages derived from error strings (no stack traces)
  - Include recovery suggestions when obvious: e.g., "Adapter not running — run `protonvpn adapter start proton` first"
  - Exit codes:
    - 0: success
    - 1: general error
    - 2: adapter/daemon communication failure
    - 3: authentication/credential error
    - 4: resource allocation failure
- Adapter crash handling:
  - MTM detects crash via `process.wait()` in background task
  - On crash: logs `ERROR`, iterates over `adapter.tunnels` dict, calls `ReleaseTunnel` for each, removes adapter from `adapter_pool`
  - No automatic restart; user must re-initiate
  - MTM does not proactively notify connected CLIs; next client operation will see connection error

### Credential Security and Ephemeral Memory

- Adapter receives credentials via **stdin** on startup (not environment variables)
- Immediately after successful VPN login:
  - Overwrite credential buffers with null bytes (zeroization)
  - Delete references (`del`, set to `None`)
- Adapter memory retains **only** VPN protocol session tokens/keys (e.g., access tokens, session cookies, WireGuard private key) for as long as needed to operate tunnels
- Plaintext username/password/2FA never persist beyond login completion
- When adapter process exits, OS reclaims all memory

---

### Claude's Discretion

- Exact error message wording (keep user-friendly but concise)
- Correlation ID format for logs (UUID? short hash?)
- Dummy adapter's namespace simulation logic (real namespace created? just name?)
- Socket directory permissions enforcement strategy (umask vs explicit chmod)
- Retry count/backoff for transient errors (currently "retry once")
- Adapter spawn timeout duration (10s is suggested, but can adjust)

---

</decisions>

<canonical_refs>
## Canonical References

**Downstream agents MUST read these before planning or implementing.**

### Architecture Specification

- `multi-tunnel-namespace/docs/NEW_ADAPTER_ARCHITECTURE_SPECIFICATION.md` — Complete design specification, including component diagram, communication channels, detailed flow examples, and security considerations

### Codebase Conventions

- `.planning/codebase/ARCHITECTURE.md` — Existing architecture analysis: Two-tier daemon with adapter pattern, concurrency model, extension points
- `.planning/codebase/CONVENTIONS.md` — Coding standards and patterns (if exists)
- `.planning/codebase/STRUCTURE.md` — Project structure and file organization

---

</canonical_refs>

<code_context>
## Existing Code Insights

### Reusable Assets

- `daemon/daemon.py` — Existing D-Bus daemon with some adapter management; needs refactor to spawn separate processes and track `adapter_pool`
- `libvpnmanager/adapters/base.py` — `VPNAdapter` base class; may need modifications for dual-server pattern and tunnel registry
- `daemon/adapter_registry.py` — Adapter discovery; can be reused to find adapter executables
- `daemon/resource_allocator.py` — Namespace and routing allocation; likely already implements most of the `AllocateTunnel` logic
- `libvpnmanager/client.py` — Client library; will need `start_adapter()` and `AdapterClient` additions
- `adapters/dummy/` — Existing dummy adapter implementation; can be adapted for Phase 1

### Established Patterns

- Async I/O with `asyncio` throughout
- D-Bus for IPC (existing); control channel will use Unix sockets (new)
- Pydantic models for configuration and tunnel state
- Adapter pattern: each VPN protocol encapsulated

### Integration Points

- New `StartAdapter()` D-Bus method on daemon
- New `AdapterClient` class in `libvpnmanager/client.py`
- Dummy adapter's `cli.py` implements dual-server and stdin credential reading
- MTM control socket server added alongside existing D-Bus server
- `AllocateTunnel` handler in daemon calls into `resource_allocator.py`

---

</code_context>

<specifics>
## Specific Ideas

- No specific references or examples from external products; decisions based on standard Unix/Linux practices and security best practices
- Dummy adapter should be realistic enough to test the actual control protocol flow but without real network operations

---

</specifics>

<deferred>
## Deferred Ideas

- Session token authentication on control channel (Phase 2/4 security hardening)
- Adapter internal credential map and protocol-specific multi-session logic (beyond simple global session)
- NTM integration: firewall rules, traffic manager requests, per-tunnel policies
- Structured logging (JSON) and correlation IDs
- Persistent AdapterClient connections for real-time traffic stats and signals
- Adapter auto-reconnect and token refresh
- Full suite of integration tests (TST-01, TST-02, TST-03) — planning will include but implementation later

---

</deferred>

---

*Phase: 01-foundation*
*Context gathered: 2025-03-20*
