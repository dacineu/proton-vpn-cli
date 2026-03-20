---
phase: 01-foundation
plan: 02
subsystem: infra
tags: [unix-socket, control-protocol, session-token, tunnel-management, crash-cleanup]

# Dependency graph
requires:
  - phase: 01-foundation/01-daemon-extensions
    provides: adapter lifecycle management, session token infrastructure, StartAdapter RPC
provides:
  - Control protocol extension with Register message handshake
  - AdapterRegistry tracks session_id, username, and tunnel set per adapter
  - ResourceAllocator validates session tokens and tracks tunnel allocations
  - Crash cleanup automatically releases all tunnels when adapter process exits unexpectedly
affects:
  - 01-foundation/03-dummy-adapter (will implement adapter control protocol)
  - 01-foundation/04-client-library (will use control protocol)
  - 01-foundation/05-testing-compatibility (will verify crash scenarios)

# Tech tracking
tech-stack:
  added: []
  patterns:
    - Bidirectional link: AdapterRegistry <-> ResourceAllocator for crash cleanup
    - SO_PEERCRED authentication for internal Unix socket connections
    - Length-prefixed JSON messages for adapter-to-daemon communication
    - Tunnel ownership tracking via per-adapter set
    - Async cleanup using asyncio.create_task to avoid blocking unregister
key-files:
  created: []
  modified:
    - multi-tunnel-namespace/src/daemon/resource_allocator.py
    - multi-tunnel-namespace/src/daemon/adapter_registry.py
    - multi-tunnel-namespace/src/daemon/daemon.py

key-decisions:
  - "Store expected_session_token in AdapterInstance and validate on each allocate/release message"
  - "Use adapter.tunnels set to track active tunnel allocations per adapter"
  - "Trigger cleanup in _unregister_by_pid using create_task to avoid blocking unregister flow"
  - "Include session_token in adapter stdin payload during spawn for control message authentication"

patterns-established: []

requirements-completed: []

# Metrics
duration: 44s
completed: 2026-03-20
---

# Phase 01-foundation: Plan 02 - Control Protocol Summary

**Control protocol with adapter registration, session token validation, per-adapter tunnel tracking, and crash cleanup**

## Performance

- **Duration:** 44s
- **Started:** 2026-03-20T17:16:39Z
- **Completed:** 2026-03-20T17:17:23Z
- **Tasks:** 5 total (1-4 already complete from prior work, 5 implemented now)
- **Files modified:** 3

## Accomplishments

- Control protocol now supports `Register` message from adapters establishing session_id, username, and session_token
- ResourceAllocator validates session_token on allocate/release requests if token is expected
- AdapterRegistry stores tunnel ownership sets and integrates with ResourceAllocator for crash cleanup
- When an adapter process crashes or exits unexpectedly, all its tunnels are automatically released
- Missing `set_resource_allocator` method added to AdapterRegistry to complete bidirectional linking
- Session token propagation from daemon to adapter fixed in start-up sequence

## Task Commits

Each task was addressed atomically:

1. **Task 1: Add Register message handling to ResourceAllocator** - Already complete (existing code in prior commits)
2. **Task 2: Implement session token validation on control messages** - `2c3b767` (fix: include session_token in adapter startup payload)
3. **Task 3: Modify AllocateTunnel handler to track tunnels per adapter** - Already complete (existing code)
4. **Task 4: Modify ReleaseTunnel handler to remove from adapter.tunnels** - Already complete (existing code)
5. **Task 5: Add adapter crash cleanup** - `4e135b3` (feat: release_adapter_tunnels method and registry integration)

**Plan metadata:** `ac51169` (prior work completing Tasks 1-4 infrastructure)

## Files Created/Modified

- `multi-tunnel-namespace/src/daemon/resource_allocator.py` - Added `release_adapter_tunnels` method; existing `_handle_register`, token validation, tunnel tracking
- `multi-tunnel-namespace/src/daemon/adapter_registry.py` - Added `set_resource_allocator` method; updated `_unregister_by_pid` to trigger crash cleanup
- `multi-tunnel-namespace/src/daemon/daemon.py` - Modified `_spawn_adapter` to include `session_token` in startup payload

## Decisions Made

- Use simple token equality check rather than complex cryptographic validation in Phase 1
- Keep crash cleanup fire-and-forget via `asyncio.create_task` to not delay unregister
- Ensure `release_adapter_tunnels` checks for existing `tunnels` attribute before iterating
- Store token in AdapterInstance as `expected_session_token` to allow optional validation (only when set)

## Deviations from Plan

None - plan executed exactly as written. All required functionality was either already present or added as specified.

## Issues Encountered

- Missing `set_resource_allocator` method in AdapterRegistry prevented crash cleanup wiring (added as part of Task 5)
- Session token not passed to adapter during spawn would break token validation (fixed in Task 2 integration)

## User Setup Required

None - no external service configuration required.

## Next Phase Readiness

- Control protocol and adapter management infrastructure is complete and ready for integration testing
- Dummy adapter (Plan 03) can now implement the control protocol side (Register, Allocate, Release)
- Client library (Plan 04) can connect to daemon and exercise the full flow

## Self-Check

**Status:** PASSED

- SUMMARY.md exists
- Commit 2c3b767 verified (Task 2 fix)
- Commit 4e135b3 verified (Task 5 implementation)
- Commit ac51169 verified (prior work)

---

*Phase: 01-foundation*
*Completed: 2026-03-20*
