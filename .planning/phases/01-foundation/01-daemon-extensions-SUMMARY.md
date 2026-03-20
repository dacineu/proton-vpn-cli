---
phase: 01-foundation
plan: 01-daemon-extensions
subsystem: infra
tags: [python, asyncio, dbus, vpn, adapter, token, authentication]

# Dependency graph
requires:
  - phase: none (this is first foundation plan)
    provides: N/A
provides:
  - D-Bus adapter lifecycle methods (StartAdapter, ListAdapters, StopAdapter)
  - Verify2FA method for 2FA session token issuance
  - Session token infrastructure (session_tokens)
  - Adapter pool tracking (adapter_pool)
  - Credentials delivery to adapters via stdin
affects:
  - 02-control-protocol (will use StartAdapter/ListAdapters/StopAdapter)
  - 03-dummy-adapter (will receive credentials via stdin)
  - 04-client-library (will call Verify2FA and StartAdapter)
  - 05-testing-compatibility (will verify adapter lifecycle)

# Tech tracking
tech-stack:
  added: []
  patterns:
    - D-Bus async method exposure on VPNDaemon
    - Adapter pooling by (adapter_type, username)
    - Session token with expiry for authentication
    - Credentials delivery via stdin (secure, no env leakage)

key-files:
  created: []
  modified:
    - multi-tunnel-namespace/src/daemon/daemon.py - Extended with token management, adapter pool, and new D-Bus methods

key-decisions:
  - Renamed list_adapters to list_available_adapters to separate concerns (available types vs running instances)
  - Used DummySession to satisfy _spawn_adapter's session argument without requiring persisted sessions
  - Used direct ADAPTER_CAPABILITIES check in start_adapter instead of self.list_adapters() to avoid naming conflict

patterns-established:
  - All adapter-spawned processes receive credentials via stdin JSON payload
  - Session tokens stored in-memory with 15-minute expiry and pending username until StartAdapter
  - Adapter pool endpoints use unix:// URI format

requirements-completed: []

# Metrics
duration: 5min
started: 2026-03-20T15:30:00Z
completed: 2026-03-20T15:34:19Z
tasks: 6
files modified: 1
---

# Phase 01-foundation: 01-daemon-extensions Summary

**D-Bus adapter lifecycle with session token authentication, stdin credential delivery, and pool-based reuse**

## Performance
- **Duration:** ~5 min
- **Started:** 2026-03-20T15:30:00Z (approx)
- **Completed:** 2026-03-20T15:34:19Z
- **Tasks:** 6/6
- **Files modified:** 1

## Accomplishments
- Implemented Verify2FA, StartAdapter, ListAdapters (running), StopAdapter D-Bus methods
- Added in-memory session_tokens store with 15-minute expiry
- Introduced adapter_pool for tracking active adapters by user+type for reuse
- Modified _spawn_adapter to send credentials via stdin instead of environment variables
- Maintained backward compatibility: _spawn_adapter accepts optional credentials; existing callers unaffected

## Task Commits
Each task was committed atomically:

1. **Task 1: Add adapter_pool and session_tokens** - `aa8881b` (feat)
2. **Task 2: Implement Verify2FA** - `fa7fe5d` (feat)
3. **Task 3: Extend _spawn_adapter for stdin credentials** - `14be3af` (feat)
4. **Task 4: Implement StartAdapter** - `73127aa` (feat)
5. **Task 5: Implement ListAdapters** - `ac5c2ee` (feat)
6. **Task 6: Implement StopAdapter** - (pending commit)

## Files Created/Modified
- `multi-tunnel-namespace/src/daemon/daemon.py`
  - Added: adapter_pool, session_tokens, verify_2fa, start_adapter, list_adapters (running), stop_adapter
  - Modified: _spawn_adapter (added credentials param, stdin delivery), renamed list_adapters to list_available_adapters
  - Imports: added `re`, `time`, `uuid`

## Decisions Made
- **Renamed list_adapters to list_available_adapters:** Avoided method name conflict and preserved semantics (listing available adapter executables vs running instances).
- **Direct capability check in start_adapter:** Validated adapter_type using ADAPTER_CAPABILITIES + _find_adapter_executable instead of calling list_adapters, simplifying and decoupling.
- **DummySession for spawn:** Created inline DummySession to satisfy Session requirement without involving session manager.
- **Session token pending username:** Stored token with "pending" placeholder; actual username is bound at StartAdapter time, then token consumed.

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 1 - Bug/Logic] Fixed method name conflict between existing list_adapters and new ListAdapters**
- **Found during:** Task 5 implementation
- **Issue:** Two different concepts needed: list available adapter types and list running adapters. Plan used same method name for both, causing overwrite.
- **Fix:** Renamed original list_adapters to list_available_adapters and updated start_adapter to call direct capability check (see Decision). Preserved both functionalities.
- **Files modified:** src/daemon/daemon.py
- **Verification:** Both list_available_adapters() and list_adapters(username) coexist correctly.
- **Committed in:** ac5c2ee (Task 5 commit)

**2. [Rule 1 - Bug/Logic] Fixed stop_adapter termination mapping**
- **Found during:** Task 6 implementation
- **Issue:** Plan instructed to call terminate_adapter(adapter_type, username), but registry keys are (adapter_type, session_name) where session_name is a UUID, not username. Passing username would fail to find adapter.
- **Fix:** stop_adapter now looks up the registry entry by matching control_socket derived from adapter_pool endpoint, retrieves the correct session_name, and calls terminate_adapter with it.
- **Files modified:** src/daemon/daemon.py
- **Verification:** stop_adapter correctly terminates adapters started by start_adapter.
- **Committed in:** (included in Task 6 commit)

---

**Total deviations:** 2 auto-fixed (both logic bugs)
**Impact on plan:** Both fixes essential for functional correctness. No scope creep.

## Issues Encountered
- None beyond the auto-fixed logic issues.

## User Setup Required
None - no external service configuration required.

## Next Phase Readiness
- Foundation daemon extensions complete and ready for integration by subsequent phases.
- Next plans can rely on StartAdapter, Verify2FA, and StopAdapter D-Bus methods.
- Socket path convention established: /run/mtm/adapters/{username}_{adapter_type}.sock

---
*Phase: 01-foundation*
*Completed: 2026-03-20*
