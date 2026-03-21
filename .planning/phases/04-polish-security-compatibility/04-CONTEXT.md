# Phase 4: Polish, Security & Compatibility — Context

**Gathered:** 2025-03-21
**Status:** Ready for planning

---

<domain>
## Phase Boundary

Harden security boundaries, ensure full backward compatibility of legacy API, complete integration testing, and deliver documentation. This phase finalizes the product for v1.0 release.

**In scope:**
- Socket permission hardening, `SO_PEERCRED` enforcement
- TOTP encryption on all communication channels (CLI↔MTM, Adapter↔MTM, CLI↔Adapter)
- Legacy D-Bus API forwarding with TOTP configuration
- Integration test suite (stubs now; fill after implementation)
- Documentation consolidation and developer guide

**Out of scope:**
- Actual test implementation (stubs only; filled in final verification)
- End-to-end performance tuning
- Production deployment automation

---

</domain>

<decisions>
## Implementation Decisions

### TOTP Security Layer (Dynamic Configuration)

- MTM daemon flag: `--totp=on|off` (default: `off`)
- TOTP disabled when external PGP service unreachable (auto-fail safe)
- System operates without TOTP when disabled/unreachable (no warnings)
- Users may still be prompted for TOTP code if service reachable; if service not reachable, connection proceeds without TOTP check
- This allows intranet-only deployments or admin opt-out

### TOTP Encryption Model

- All data flows encrypted/decrypted using current TOTP value as symmetric key
  - CLI → MTM (D-Bus)
  - MTM ↔ Adapter (control channel)
  - CLI ↔ Adapter (tunnel operations)
- Key derivation: Use TOTP directly (no HKDF) — current 6-digit code converted to bytes, possibly zero-padded to 16/32 bytes
- Single TOTP secret per user; each adapter session uses same TOTP per session
- TOTP secrets **not stored** in MTM: downloaded from external PGP service on-demand, kept in memory transiently
- If external service unreachable during operation, fall back to unencrypted mode (system continues to function)

### Legacy D-Bus API Forwarding

- Legacy D-Bus methods (`CreateTunnel`, `ConnectTunnel`, `DisconnectTunnel`, `DestroyTunnel`, `ListTunnels`, `GetTunnelStatus`) preserved
- Implementation forwards internally:
  1. Legacy call arrives at D-Bus service
  2. If adapter not running, call `StartAdapter` (with session token handling)
  3. Forward request to adapter via control socket (transparent to caller)
- Legacy API respects `--totp` flag:
  - When `--totp=on`: Legacy calls must include session token (same as new API)
  - When `--totp=off`: Legacy calls accepted without session token (backward compatible)
- No deprecation warnings in this release (silent operation)

### Socket Permissions & Authenticity

- Adapter CLI sockets: `0600`, owned by the user who started the adapter (as configured)
- Control socket (MTM ↔ Adapter): `0660` to allow MTM (root) and adapter (user) group access
- `SO_PEERCRED` used on control socket to verify connecting process is a child of MTM (PID matches registry entry)
- Adapter CLI socket permissions verified in integration test (manual check in TST-01)

### Test Strategy (Phase 4)

- Create **empty test stubs** for all integration tests (TST-01, TST-02, TST-03)
- Stubs include test function signatures and basic assertions; implementation deferred
- Full test implementation occurs after all phases complete (final verification stage)
- Stubs ensure test structure is defined; filling them later validates correct behavior

### Documentation Organization

- **Single primary architecture document** (merged from existing design docs) in `docs/` root
- **Dual documentation tree**:
  - `docs/user/` — End-user facing: architecture overview, migration guide, usage concepts
  - `docs/developer/` — Developer facing: implementation details, adapter guide, protocol specs, testing strategies
- `docs/INDEX.md` acts as navigation hub, pointing to documents in both subdirectories
- Migration guide (DOC-02) placed in `docs/developer/` as it explains session persistence removal and system changes
- Developer adapter implementation guide (DOC-03) either extracted from `ADAPTER_INTEGRATION.md` or referenced directly if already complete

### Keyring & PGP Service Integration (Plan Item)

- Use `keyring` Python package for keyring access (cross-platform abstraction)
- External PGP service stores per-user TOTP secrets; MTM downloads on-demand during user session setup
- TOTP secrets remain only in transient memory; zeroized after use or on shutdown
- Plan includes task to "harden keyring integration with external PGP service" (add to Phase 4 plan)
- No local persistence of TOTP secrets; if external service unavailable, TOTP layer stays disabled

---

</decisions>

<canonical_refs>
## Canonical References

**Downstream agents MUST read these before planning or implementing.**

### Phase Requirements & Specification

- `.planning/REQUIREMENTS.md` — Full v1 requirements (DAEM, ADPT, CLI, COMP, SEC, TST, DOC)
- `docs/NEW_ADAPTER_ARCHITECTURE_SPECIFICATION.md` — Original design specification: component diagram, communication channels, flow examples
- `docs/DBUS_SECURITY_AND_ARCHITECTURE.md` — D-Bus security model, legacy API details
- `docs/ADAPTER_INTEGRATION.md` — Proton adapter integration specifics, required daemon changes for multi-tunnel support

### Codebase Conventions

- `.planning/codebase/CONVENTIONS.md` — Coding standards (black, ruff, mypy, error handling)
- `.planning/codebase/ARCHITECTURE.md` — Existing architecture analysis, adapter pattern, concurrency model
- `.planning/codebase/STRUCTURE.md` — Project structure and layout, entry points, package organization

### Prior Phase Context (for consistency)

- `.planning/phases/01-foundation/1-CONTEXT.md` — Phase 1 decisions: socket paths, control protocol, CLI-level 2FA, dummy adapter behavior, token model
- `.planning/phases/03-resource-management-isolation/03-CONTEXT.md` — Phase 3 decisions: namespace allocation, crash cleanup, idle timeout mechanism

---

</canonical_refs>

<code_context>
## Existing Code Insights

### Reusable Assets

- `daemon/resource_allocator.py` — Already implements `SO_PEERCRED` authentication for control socket; need to add TOTP validation per request
- `daemon/daemon.py` — Main daemon; need to add `--totp` flag parsing and external PGP service client integration
- `libvpnmanager/ipc/unix_socket.py` — Unix socket server/client with permissions; socket mode already 0600/0660
- `libvpnmanager/sessions/manager.py` — Session storage; may need modification to avoid TOTP secret persistence
- `libvpnmanager/dbus/service.py` — D-Bus service with legacy methods; will implement forwarding to adapter

### Established Patterns

- Async I/O with `asyncio` throughout; need to keep non-blocking for external PGP calls
- NDJSON framing for control channel (length-prefixed JSON actually); reuse for encryption layer
- Token-based session authentication (Phase 1): adapter stores `expected_session_token`; can extend with TOTP
- Dummy adapter pattern provides reference for dual-server architecture

### Integration Points

- New `--totp` flag on `VPNDaemon.__init__` and command-line entry point
- External PGP service client: new module `mtm/pgp_service.py` (or similar)
- Modified `start_adapter`: download user's TOTP secret from PGP service before spawn, pass to adapter via stdin (already includes stdin mechanism)
- Adapter stdin payload augmentation: include `totp_secret` (already in Phase 1 spec but not implemented)
- Control socket handler (`ResourceAllocator._dispatch`): add TOTP verification per message using stored secret
- Adapter CLI request handler: validate TOTP on each CLI→Adapter message
- D-Bus legacy method implementations: refactor to call `manager.start_adapter` then forward via `AdapterClient`

---

</code_context>

<specifics>
## Specific Ideas

- TOTP encryption should be "transparent" — existing message formats unchanged; payload encrypted/decrypted at transport layer (like TLS with TOTP as pre-shared key)
- When external PGP service down, MTM logs a warning at startup but continues to run with TOTP disabled; no blocking startup failure
- Migration guide should clearly state: "Session persistence removed; you must log in after each adapter restart" along with TOTP changes
- Developer docs should include an "Adapter Implementation Checklist" covering: dual-server, stdin credentials, TOTP validation, namespace coordination, crash handling

---

</specifics>

<deferred>
## Deferred Ideas

- Full TOTP encryption implementation details (HKDF vs direct use) left to planner/researcher discretion
- Runtime reconfiguration of `--totp` (hot-reload) — out of scope; requires daemon restart
- External PGP service client fallback chain (multiple PGP servers) — simplified to single service; add later if needed
- Advanced threat model: encrypt process memory against swap, use `mlock` — defer to security audit post-v1.0
- CLI subcommand to manually refresh TOTP secret from PGP service — not needed; automatic on adapter spawn

---

</deferred>

---

*Phase: 04-polish-security-compatibility*
*Context gathered: 2025-03-21*
