---
phase: 01-foundation
plan: 03
subsystem: infra
tags: [dummy-adapter, unix-socket, control-protocol, session-token, tunnel-management, asyncio]

# Dependency graph
requires:
  - phase: 01-foundation
    plan: 02
    provides: control protocol with Register, session token validation, resource allocation via internal socket
provides:
  - Standalone dummy adapter executable (`mtm-adapter-dummy`) with dual-server architecture
  - CLI Unix socket server handling newline-delimited JSON requests
  - Control client to MTM internal socket using length-prefixed JSON
  - Startup stdin credential reading with zeroization
  - Tunnel lifecycle: CreateTunnel (with AllocateTunnel), DestroyTunnel (with ReleaseTunnel), ListTunnels, GetStatus
  - Per-adapter tunnel tracking with asyncio.Lock for concurrency
  - Session token validation on CLI requests (INVALID_SESSION on mismatch)
  - Graceful shutdown via SIGTERM/SIGINT with resource cleanup
affects:
  - 01-foundation/04-client-library (will connect to adapter endpoint)
  - 01-foundation/05-testing-compatibility (will verify adapter crash cleanup and protocol)

# Tech tracking
tech-stack:
  added: []
  patterns:
    - Dual-server process: CLI Unix socket + control client to MTM
    - Length-prefixed JSON for control channel, newline-delimited JSON for CLI
    - Credentials delivered via stdin with buffer zeroization
    - Session token binding between CLI and adapter
    - Lock-based concurrency control on shared tunnel dict
key-files:
  created: []
  modified:
    - multi-tunnel-namespace/src/adapters/dummy_adapter/cli.py
key-decisions:
  - "Adapter stores session_token from stdin for CLI request validation (not from Register response)"
  - "Simulate VPN login with 0.5s delay and varying device names (dummy0, dummy1, ...)"
  - "Use global state with asyncio.Lock to protect concurrent tunnel operations"
patterns-established: []
requirements-completed: []

# Metrics
duration: 2 min
completed: 2025-03-20
---

# Phase 01-foundation: Plan 03 - Dummy Adapter Summary

**Dummy adapter executable with dual-server architecture, control protocol integration, and session-secured CLI**

## Performance

- **Duration:** 2 min
- **Started:** 2025-03-20T17:30:20Z
- **Completed:** 2025-03-20T17:32:05Z
- **Tasks:** 6 (5 functional commits)
- **Files modified:** 1

## Accomplishments

- Created standalone `mtm-adapter-dummy` entry point with fully functional CLI server and control client
- Implemented all required tunnel operations: CreateTunnel, DestroyTunnel, ListTunnels, GetStatus
- Integrated AllocateTunnel and ReleaseTunnel control messages with MTM's resource allocator
- Added session token validation on every CLI request to enforce CLI-adapter authentication
- Implemented graceful shutdown handling with signal registration and cleanup
- Ensured file permissions (socket 0o600) and executable bit

## Task Commits

Each task was addressed atomically:

1. **Task 1: Create dummy adapter CLI module structure with async main** - `9a09d6d` (feat) & `5e31d9a` (Task 2 combined due to implementation flow)
2. **Task 2: Implement CreateTunnel handler with AllocateTunnel control message** - `5e31d9a` (feat)
3. **Task 3: Implement DestroyTunnel and ListTunnels handlers** - `5e31d9a` (feat) & later modifications? Actually included in `5e31d9a`
4. **Task 4: Add session token validation to CLI request handler** - `2a5680a` (feat)
5. **Task 5: Add graceful shutdown handling** - `244dd98` (feat)
6. **Task 6: Ensure cli.py executable and entry point present** - `f18b4ac` (chore)

**Plan metadata:** `9a09d6d` (initial adapter implementation)

## Files Created/Modified

- `multi-tunnel-namespace/src/adapters/dummy_adapter/cli.py` - Core dummy adapter CLI: server startup, control protocol, tunnel handlers, signal handling, and shutdown.

## Decisions Made

- Stored `expected_session_token` from the startup stdin payload (not from Register response) because the daemon already passes the session token directly and Register response does not contain it.
- Used `asyncio.Lock` to protect the global `tunnels` dict and counter against concurrent CLI connections.
- Simulated tunnel devices as `dummy0`, `dummy1`, ... with a 500ms–1s random delay to mimic VPN handshake.
- Chose newline-delimited JSON for CLI requests (as per spec) and length-prefixed JSON for control channel.

## Deviations from Plan

None - plan executed exactly as written. All required functionality was implemented as specified.

## Issues Encountered

None - all auto-fix rules applied during execution were within the plan scope.

## User Setup Required

None - no external service configuration required.

## Next Phase Readiness

- Client library (Plan 04) can now connect to the adapter endpoint to exercise the full flow.
- Testing compatibility (Plan 05) can verify adapter crash cleanup and protocol edge cases.

---
*Phase: 01-foundation*
*Completed: 2025-03-20*
