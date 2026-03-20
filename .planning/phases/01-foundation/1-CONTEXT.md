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

### CLI-Level 2FA with Per-Request TOTP

**Purpose:** Ensure only authorized users (possessing TOTP device) can manage VPN tunnels, independent of OS user authentication.

**Threat model:** Prevent unauthorized local use of `protonvpn` CLI commands, even by users with shell access but without TOTP device.

**Security model:** MTM is the sole keeper of the user's TOTP secret. CLI never stores secrets. Adapter receives TOTP secret at spawn and validates per-request TOTP codes. Every request (CLI→MTM, CLI→Adapter, Adapter→MTM) includes a fresh TOTP code for that time window.

**Setup Phase (One-Time):**
```
$ protonvpn setup-2fa --scan-qr  # or manual secret entry
```
- MTM generates 160-bit TOTP secret for this user
- Stores TOTP secret **encrypted** in system keyring (libsecret)
- Displays QR code and backup codes, warns user to store securely
- Secret never displayed again; cannot be retrieved from MTM

**Normal Operation Flow:**

1. **User runs command:**
   ```
   $ protonvpn tunnel create personal --country US
   TOTP Code: 123456
   ```
   CLI reads TOTP code from user (never stores it).

2. **CLI → MTM: StartAdapter with TOTP**
   ```json
   {
     "method": "StartAdapter",
     "params": {
       "adapter_type": "wireguard",
       "credentials": { "username": "...", "password": "...", "twofa": "..." },
       "totp_code": "123456"
     }
   }
   ```
   MTM:
   - Decrypts stored TOTP secret from keyring
   - Verifies `totp_code` (current ±1 time step)
   - If invalid → `INVALID_2FA` error
   - If valid → proceed to spawn adapter

3. **MTM spawns adapter:**
   - MTM passes to adapter via **stdin**:
     ```json
     {
       "session_id": "uuid",
       "totp_secret": "JBSWY3DPEHPK3PXP",
       "vpn_credentials": { ... }
     }
     ```
   - Adapter reads stdin, stores `totp_secret` in memory (for later CLI request verification)
   - Adapter immediately zeroes stdin buffer
   - Adapter binds CLI socket, connects to MTM control socket
   - Adapter sends `Register` control message (with `session_id`, `adapter_type`, `username`)
   - Adapter performs VPN login, then zeroes credential buffers (keep only VPN session tokens)
   - MTM returns to CLI: `{ "endpoint": "unix:///run/mtm/adapters/..." }` (no session token)

4. **CLI → Adapter: CreateTunnel with TOTP**
   - CLI prompts user for **another** TOTP code (fresh 30s window):
     ```
     TOTP Code: 654321
     ```
   - CLI connects to adapter socket, sends:
     ```json
     {
       "action": "CreateTunnel",
       "totp_code": "654321",
       "tunnel_name": "personal",
       "config": { ... }
     }
     ```
   - **Adapter validates TOTP:**
     - Compute expected TOTP from stored `totp_secret`
     - Constant-time compare with `totp_code`
     - Invalid → log WARNING, close connection or return `{"error": "INVALID_2FA"}`
     - Valid → process request

5. **Adapter → MTM: AllocateTunnel with TOTP**
   ```json
   {
     "action": "AllocateTunnel",
     "totp_code": "654321",
     "session_id": "uuid",
     "tunnel_name": "personal",
     "device": "...", "gateway": "...", "dns": [...]
   }
   ```
   - **MTM validates TOTP:**
     - Look up user by `session_id`
     - Decrypt user's TOTP secret from keyring
     - Verify `totp_code`
     - Invalid → reject with `INVALID_2FA`
     - Valid → allocate namespace, configure, reply

**Key properties:**
- Every request carries a fresh TOTP code (user prompted each time)
- No persistent session tokens; TOTP is the per-request credential
- TOTP secret known only to MTM (persisted encrypted) and adapter (in-memory during lifetime)
- Adapter must validate TOTP on every CLI request
- MTM must validate TOTP on every control message from adapter
- Clock skew tolerance: ±1 time step (30s) to accommodate device clock drift

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

### Token Authentication Model (CLI-Level 2FA)

**Purpose:** Ensure only authorized users (possessing TOTP device) can manage VPN tunnels, independent of OS user authentication.

**Threat model:** Prevent unauthorized local use of `protonvpn` CLI commands, even by users with shell access but without TOTP device.

**Three trusted parties:**
1. **User** — possesses OTP device (YubiKey, phone, etc.) with TOTP secret
2. **MTM** — the only component that knows the TOTP secret; stored securely (encrypted at rest using libsecret/keyring)
3. **CLI** — never stores any secrets; only holds short-lived session tokens in memory
4. **Adapter** — receives token validation capability from MTM at spawn; validates CLI's session token on each request

**Setup Phase (One-Time):**
```
$ protonvpn setup-2fa --scan-qr  # or manual secret entry
```
- MTM generates/registers a TOTP secret for this user
- Warns: "Store this 2FA key securely. It will not be shown again."
- MTM stores TOTP secret encrypted (system keyring)
- User adds secret to their OTP device

**Normal Operation Flow:**

1. **CLI session start with 2FA:**
   ```
   $ protonvpn tunnel create ...
   TOTP Code: 123456
   ```
   - CLI sends TOTP to MTM via D-Bus: `Verify2FA(totp_code)`
   - MTM checks against stored TOTP secret:
     - Valid → issues `cli_session_token` (random, 15min TTL)
     - Invalid → reject
   - CLI caches token in memory for TTL

2. **CLI → MTM D-Bus calls:**
   - Every D-Bus call includes `cli_session_token` in metadata
   - MTM validates token (exists, not expired)
   - If valid → process request
   - If invalid/expired → `AUTH_EXPIRED`, CLI re-prompts for TOTP

3. **MTM spawns adapter:**
   - MTM passes to adapter (via stdin or protected control message):
     - `session_token` (unique per adapter instance, so adapter can bind CLI to this specific adapter)
     - `cli_2fa_verification_key` (symmetric key or TOTP secret itself) so adapter can independently verify CLI's TOTP token if needed
   - Simpler: MTM includes `allowed_session_token` in `Register` response; adapter validates that incoming CLI messages present this exact token. No crypto needed.

**Design Decision: Adapter token validation simplified.**

Since MTM already verified CLI 2FA before spawning the adapter, the adapter can trust that any CLI possessing the `session_token` is legitimate. The adapter only needs to check that the `session_token` matches the one it expects for its session. This avoids:
- Passing TOTP secrets to adapters (reduces secret distribution)
- Adapter needing to validate TOTP independently (MTM already did)
- Complex key management across processes

**Protocol:**
- Adapter stores `expected_session_token` from MTM at spawn
- Every CLI→Adapter message includes `session_token`
- Adapter accepts if `msg.session_token == expected_session_token`
- No expiration check on adapter side; if MTM's token expires, adapter continues to accept it for existing session (MTM won't spawn new adapters with expired token)

**Rationale:** Trust boundary is MTM→adapter at spawn time. After that, adapter enforces session binding only. That's sufficient because:
- Only MTM can spawn adapter with a given session token
- Only CLI with valid token can connect to adapter (token acts as shared secret)
- Compromise of adapter doesn't expose TOTP secret (only the session token, which is short-lived)

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

- Real TOTP verification (Phase 4): Replace dummy tokens with actual `Verify2FA(totp_code)` using stored TOTP secret; Phase 1 implements token infrastructure without secret checks
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
