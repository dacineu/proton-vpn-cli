---
phase: 02
type: validation_strategy
---

# Phase 2 Validation Strategy

**Purpose:** Define how Phase 2's implementation will be verified to meet its goal.

**Phase Goal:** Migrate Proton adapter to new architecture; integrate CLI direct flow; implement adapter subcommands.

**Validation Approach:**

Phase 2 verification will be performed by the integration test suite created in Wave 4 (plan 02-W4). The tests will exercise:

1. **Adapter startup** - Verifies ADPT-04: adapter process spawns, binds CLI socket, accepts connections, reads stdin credentials
2. **Tunnel creation and reuse** - Verifies ADPT-04/05: multiple tunnels created from same adapter instance, session reused, no re-authentication
3. **Session token enforcement** - Verifies security: CLI requests without valid session_token rejected
4. **Concurrent connections** - Verifies ADPT-05: multiple AdapterClient connections handled safely with asyncio.Lock
5. **Adapter management** - Verifies CLI-05: `adapter list` shows running adapters; `adapter stop` terminates adapter cleanly
6. **Credential prompt logic** - Verifies CLI-04: prompt shown only when no adapter running; skipped when adapter already running
7. **Legacy API compatibility** - Verifies COMP-01/02: old ManagerClient.create_tunnel() still functions

**Automated Checks:**
- All integration tests in `test_phase2_proton_adapter.py` must pass (pytest exit code 0).
- Specific assertions:
  - `test_proton_adapter_startup`: adapter process in daemon.adapter_pool, socket exists, GetStatus returns ok
  - `test_tunnel_creation_and_reuse`: two tunnels created, both present in adapter._local_tunnels, adapter not respawned
  - `test_adapter_list_stop`: adapter appears in list, then removed after stop
  - `test_credential_prompt_shown_when_adapter_missing`: click.prompt called at least once
  - `test_credential_prompt_skipped_when_adapter_running`: click.prompt not called
  - `test_legacy_create_tunnel_still_works`: old API returns a tunnel

**Manual Verification Required (UAT):**
- None specified; all success criteria are covered by automated integration tests.
- If integration tests fail, phase verification will be blocked.

**Gaps:**
- Real Proton VPN credentials not available in CI; tests use mocks. This is acceptable for architecture validation; full end-to-end with real VPN would be Phase 3 or later.

**Acceptance:**
Phase verifier (gsd-verifier) should run the integration test suite and confirm all assertions green before marking Phase 2 complete.
