# Phase 4: Polish, Security & Compatibility — Validation Plan

**Requirements:** COMP-01, COMP-02, SEC-01, SEC-02, SEC-03, TST-01, TST-02, TST-03, DOC-01, DOC-02, DOC-03

This document defines verifiable test criteria for each requirement. These tests will be used by the Nyquist verifier to confirm phase completion.

---

## Validation Matrix

| Requirement | Test Task | Verification Method | Expected Outcome |
|-------------|-----------|---------------------|------------------|
| COMP-01 | test_legacy_create_tunnel_forwards | Integration test: call legacy D-Bus CreateTunnel with no adapter running | Adapter auto-starts, tunnel created; result equals new API |
| COMP-02 | test_legacy_destroy_tunnel, test_legacy_other_methods_forward | Integration test: call legacy DestroyTunnel, ConnectTunnel, etc. | All operations work and are forwarded to adapter |
| SEC-01 | test_adapter_cli_socket_permissions | Programmatic check after adapter spawn | `os.stat(sock_path).st_mode & 0o777 == 0o600` |
| SEC-02 | test_no_credentials_in_proc | Read `/proc/<pid>/environ` of adapter process | No strings matching credential patterns (username, password, totp) |
| SEC-03 | test_control_socket_peer_cred | Attempt connection to control socket from different UID | Connection rejected with PermissionError |
| SEC-08 | test_control_channel_encryption, test_cli_adapter_encryption | Inspect messages on wire or mock transport | When totp_enabled, messages contain `encrypted` field; when disabled, plaintext |
| TST-01 | test_full_integration_totp | Full end-to-end flow: CLI → MTM → adapter (with TOTP) → namespace → tunnel success | All assertions pass; tunnel connected; /proc/pid/environ clean |
| TST-02 | test_adapter_crash_cleanup | Start adapter with active tunnel; `kill -9` adapter; wait | MTM detects crash, removes namespace within `idle_timeout` seconds |
| TST-03 | test_concurrent_adapter_access | Multiple concurrent CLI tasks creating tunnels on same adapter | All succeed; no cross-talk; tunnel isolation maintained |
| DOC-01 | doc_architecture_complete | File existence and content check | `docs/ARCHITECTURE.md` exists, ≥2000 words, covers TOTP, sockets, legacy |
| DOC-02 | doc_migration_guide_complete | File existence and content check | `docs/developer/MIGRATION.md` exists, ≥1000 words, mentions session persistence removal and TOTP changes |
| DOC-03 | doc_adapter_guide_complete | File existence and content check | `docs/developer/ADAPTER_IMPLEMENTATION_GUIDE.md` exists, ≥1500 words, includes checklist and protocol specs |

---

## Detailed Test Specifications

### COMP-01: Legacy D-Bus CreateTunnel Forwards to Adapter

**Test:** `test_legacy_create_tunnel_forwards`

**Setup:**
- Start MTM daemon (with TOTP auto-detection; if service reachable, totp_enabled=True)
- Ensure no adapter is running for the test user
- Connect via legacy D-Bus interface (use ManagerService from `libvpnmanager.dbus.service`)

**Steps:**
1. Call `CreateTunnel` on D-Bus with parameters:
   - `username`: test user
   - `config`: dict with `adapter='dummy'`, `tunnel_name='test'`, `vpn_username`, `password`, etc.
   - Omit session token if TOTP disabled; provide valid session token if TOTP enabled (obtained via prior Verify2FA call)
2. Observe that `CreateTunnel` returns success with tunnel info (endpoint, device, namespace)

**Assertions:**
- Adapter process was spawned (check process list or log).
- The D-Bus call returns the same structure as the new `AdapterClient.create_tunnel` would return.
- The tunnel appears in `ListTunnels` (both legacy and new API).
- No direct call to `VPNDaemon.create_tunnel` was made (can verify via mock or log inspection).

**Failure Conditions:**
- `CreateTunnel` raises `AdapterNotFoundError` when no adapter running (should auto-start).
- Return format differs from expected.

---

### COMP-02: Legacy D-Bus Other Methods Work

**Tests:** `test_legacy_destroy_tunnel`, `test_legacy_connect_tunnel`, `test_legacy_disconnect_tunnel`, `test_legacy_get_tunnel_status`, `test_legacy_list_tunnels`

**Setup:** Same as above; first create a tunnel to have something to operate on.

**Steps:** For each method, call via D-Bus and assert correct behavior:
- `DestroyTunnel(tunnel_name)`: tunnel removed, adapter stays running (or stops if last tunnel and policy dictates)
- `ConnectTunnel(tunnel_name)`, `DisconnectTunnel(tunnel_name)`: state changes as expected
- `GetTunnelStatus(tunnel_name)`: returns status dict
- `ListTunnels()`: returns list of all tunnels across all adapters

**Assertions:** Each method returns appropriate result without raising unexpected errors.

---

### SEC-01: Adapter CLI Socket Permissions

**Test:** `test_adapter_cli_socket_permissions`

**Setup:** Start MTM daemon and trigger adapter spawn (via CLI or D-Bus).

**Steps:**
1. Determine the adapter CLI socket path (expected pattern: `/run/mtm/adapters/<username>_<adapter_type>.sock`)
2. After adapter binds, run `os.stat(sock_path)`
3. Check mode: `(stat_result.st_mode & 0o777) == 0o600`

**Assertions:** Socket file is readable/writable only by owner (user).

---

### SEC-02: Credentials Not Exposed in /proc

**Test:** `test_no_credentials_in_proc`

**Setup:** Start adapter with known credentials (password: "Secret123", TOTP secret known).

**Steps:**
1. Get adapter's PID (from `ps` or daemon registry).
2. Read `/proc/<pid>/environ` as binary, decode to string (null-separated).
3. Search for occurrences of credential strings: username, password, TOTP secret (base64 form).
4. Also check that the adapter's memory (if feasible) does not contain plaintext credentials — this may be manual or via code review.

**Assertions:** No credential substrings found in environment. The adapter should have received credentials via stdin, not env.

---

### SEC-03: Control Socket SO_PEERCRED Verification

**Test:** `test_control_socket_peer_cred`

**Setup:** Start MTM daemon; note control socket path (e.g., `/run/mtm/control/mtm.sock`).

**Steps:**
1. Attempt to connect to the control socket as a different UID (e.g., using `sudo -u nobody` or another user in test environment).
2. Try to send a fake `Register` message or just open connection.
3. Expect connection to be rejected (connection refused or closed immediately).

**Assertions:** Unauthorized process cannot establish connection to control socket.

---

### SEC-08: TOTP Encryption on Communication Channels

**Tests:** `test_control_channel_encryption`, `test_cli_adapter_encryption`, `test_encryption_with_totp_disabled`

**Setup:** Need to run daemon with TOTP mode enabled. Since PGP service is stub, we can patch `totp_service.get_user_totp_secret` to return a real secret (e.g., base64 of "mysecret").

**Steps for control channel:**
1. Start daemon; ensure `totp_enabled=True` (might need to mock health check to return True and stub secret fetch to return a known secret).
2. Start an adapter (dummy).
3. Trigger a control message from adapter to MTM (e.g., `AllocateTunnel`).
4. Intercept the message on the socket (using a mock transport or by patching the server to log raw bytes).
5. Assert that the message JSON includes `"totp"` and `"encrypted"` fields; plaintext not visible.

**Steps for CLI→Adapter:**
1. With adapter running and `totp_secret` set, use `AdapterClient` with a `totp_code` to call `create_tunnel`.
2. Capture the bytes sent on the socket.
3. Assert envelope format with `totp` and `encrypted`.
4. Decrypt using `totp_crypto.decrypt_message` and verify plaintext is correct.

**With TOTP disabled:** Same tests should show plaintext messages without envelope.

---

### TST-01: Full Integration Flow

**Test:** `test_full_integration_totp`

**Scope:** End-to-end test covering:
- Daemon startup with TOTP (mocked)
- CLI calls `start_adapter` (or legacy `CreateTunnel`)
- Adapter spawns with `totp_secret`
- Adapter registers with MTM
- CLI (or legacy) calls `create_tunnel`
- Adapter creates tunnel, `AllocateTunnel` with encryption
- Namespace created
- Tunnel info returned to CLI
- Clean shutdown

**Assertions:** All steps succeed, no credential leakage (can check adapter's stdin buffer after read is zeroed via code inspection), correct socket permissions.

---

### TST-02: Adapter Crash Recovery

**Test:** `test_adapter_crash_cleanup`

**Setup:** Start adapter, create at least one tunnel.

**Steps:**
1. Get the namespace name used (from tunnel info).
2. Kill the adapter process with `SIGKILL` (simulate crash).
3. Wait for `idle_timeout` period (or trigger immediate cleanup if daemon detects via `asyncio.wait`).
4. Check that the namespace no longer exists: `ip netns list` should not show that namespace.

**Assertions:** MTM detects adapter death and cleans up associated tunnel resources (network namespace, veth pair, etc.) within expected timeframe.

---

### TST-03: Concurrent Access

**Test:** `test_concurrent_adapter_access`

**Setup:** Start a single adapter for a user.

**Steps:**
1. Spawn multiple concurrent CLI clients (asyncio tasks or separate processes) connecting to the same adapter.
2. Each client calls `create_tunnel` with a unique tunnel name.
3. Wait for all operations to complete.

**Assertions:** All tunnels created successfully, no cross-talk (each tunnel has correct config), adapter's internal state is consistent (no race conditions), no exceptions other than expected.

---

### DOC-01: Architecture Documentation Complete

**Check:** `doc_architecture_complete`

**Criteria:**
- File `docs/ARCHITECTURE.md` exists.
- Word count ≥ 2000.
- Contains sections on:
  - Component overview (MTM, adapters, CLI, D-Bus)
  - Adapter lifecycle
  - Communication channels (D-Bus, control, CLI) with TOTP encryption envelope
  - Security model (socket permissions, SO_PEERCRED, stdin credentials, memory sanitation, TOTP two-layer)
  - Legacy D-Bus forwarding
  - Configuration (TOTP service auto-discovery)
  - Cross-references to other specs
- Includes at least one diagram (ASCII or mermaid).

---

### DOC-02: Migration Guide Complete

**Check:** `doc_migration_guide_complete`

**Criteria:**
- File `docs/developer/MIGRATION.md` exists.
- Word count ≥ 1000.
- Covers:
  - Summary of changes
  - **Session persistence removal** (explicit statement: "Session persistence removed; you must log in after each adapter restart.")
  - TOTP two-factor changes (auto-detection, no flag)
  - Adapter management commands
  - Configuration changes
  - Impact on scripts/automation
  - Troubleshooting
  - Rollback instructions
- References architecture and adapter guide.

---

### DOC-03: Adapter Implementation Guide Complete

**Check:** `doc_adapter_guide_complete`

**Criteria:**
- File `docs/developer/ADAPTER_IMPLEMENTATION_GUIDE.md` exists.
- Word count ≥ 1500.
- Contains sections:
  - Overview, Project Setup, Dual-Server Pattern, Startup Sequence, Control Protocol, Tunnel Management, TOTP Encryption Integration, Crash Handling, Testing, Debugging, Checklist
- Includes code snippets for:
  - Reading stdin and storing totp_secret
  - Sending/receiving encrypted control messages
  - Verifying TOTP on CLI requests
  - Zeroizing credentials
- References PROTOCOL_SPECS.md and ARCHITECTURE.md.

---

## Manual Verification Steps

For items not easily automated:

1. **Socket permissions**: Run integration test that spawns adapter and checks `os.stat`.
2. **SO_PEERCRED**: Manual test with separate user connection attempt (could be a shell script).
3. **Credential leakage**: Read `/proc/<pid>/environ` and grep; also perform code review for zeroization patterns.
4. **Encryption**: Mock totp_service to return secret; inspect captured messages on the socket (use a proxy or patched transport).
5. **Crash cleanup**: Manual kill and observe namespace removal.
6. **Concurrent access**: Run test suite with multiple clients.
7. **Documentation completeness**: Automated checks for file existence and word count; manual review for required sections.

---

## Validation Execution Order

1. Run automated checks for DOC-* (file existence, word count).
2. Run integration tests for SEC-*, COMP-*, TST-* (after implementation is done).
3. Perform manual checks for SO_PEERCRED and encryption (if not automated).
4. Compile results into VERIFICATION.md.

---

*Phase: 04-polish-security-compatibility*
*Validation plan created: based on RESEARCH.md and REQUIREMENTS.md*