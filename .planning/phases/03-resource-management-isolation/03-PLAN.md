# Phase 3: Resource Management & Isolation — Implementation Plan

**Phase:** 03 — resource-management-isolation
**Goal:** Implement namespace allocation and cleanup in MTM; ensure proper network isolation; add adapter lifecycle management (crash detection, idle timeout)
**Requirements:** DAEM-03, DAEM-04, DAEM-05, DAEM-06
**Mode:** Standard (2 plans)

---

## Execution Plan Overview

| Wave | Plans | What it builds |
|------|-------|----------------|
| 1 | 01 | Full AllocateTunnel integration: device movement + network configuration |
| 2 | 02 | Configurable idle timeout + Phase 3 test coverage |

---

## Plan 01: Full AllocateTunnel Resource Allocation Integration

**Objective:** Complete the AllocateTunnel handler to perform full resource allocation (namespace creation, device movement, network configuration, DNS setup) as required by DAEM-03.

**Wave:** 1
**Depends on:** Phase 02 complete (adapter integration)
**Files modified:**
- `src/daemon/resource_allocator.py` – AllocateTunnel handler implementation
- `src/libvpnmanager/routing/namespace.py` – NetworkNamespaceRouting methods (add_device_movement, add_network_configuration)
- `src/adapters/proton_vpn_adapter/cli.py` – AllocateTunnel request composition (include device, gateway, dns, vpn_ip)
- Possibly `src/libvpnmanager/models/tunnel.py` – Tunnel fields for gateway/dns if needed

**Tasks:**

### Task 1.1: Update AllocateTunnel request from adapter to include device, gateway, DNS, and VPN IP

**Read first:**
- `src/adapters/proton_vpn_adapter/cli.py` (current AllocateTunnel composition)
- `src/adapters/proton_vpn_adapter/adapter.py` (Tunnel object fields)

**Action:**
Modify `create_tunnel` CLI handler in `adapters/proton_vpn_adapter/cli.py`:
After `adapter_instance.create_tunnel()` returns a Tunnel object, extract:
- `device` from `tunnel.device`
- `gateway` from available Tunnel metadata or config (determine source during implementation)
- `dns` from available Tunnel metadata or config (determine source during implementation)
- `vpn_ip` from available Tunnel metadata or config (client-assigned IP)

Include these fields in the `allocate_req` payload:
```python
allocate_req = {
    'msg_type': 'allocate',
    'tunnel_name': tunnel_name,
    'device': device,          # NEW
    'gateway': gateway,        # NEW
    'dns': dns,                # NEW (list)
    'vpn_ip': vpn_ip,          # NEW (client IP for /32 config)
    'username': adapter_username
}
```

**Acceptance criteria:**
- `grep "allocate_req = {" src/adapters/proton_vpn_adapter/cli.py` shows the request includes `'device'`, `'gateway'`, `'dns'`, `'vpn_ip'` keys
- The values are sourced from the Tunnel object or derived from connection metadata
- Test: Sending a CreateTunnel CLI request includes these fields in the AllocateTunnel control message

---

### Task 1.2: Update ResourceAllocator._handle_allocate to accept and validate new fields

**Read first:**
- `src/daemon/resource_allocator.py` (current _handle_allocate implementation)
- `src/libvpnmanager/routing/namespace.py` (create_tunnel_context, move_device_to_namespace, configure_namespace_network)

**Action:**
In `src/daemon/resource_allocator.py`, modify `_handle_allocate()`:
1. Extract required fields from request:
   - `tunnel_name` (required)
   - `device` (required, non-empty string)
   - `gateway` (required, non-empty string, IP address format)
   - `dns` (required, list of IP strings, may be empty)
   - `vpn_ip` (required, string, IP address format)
2. Validate presence and basic format (raise error if missing)
3. Call `await self.routing.create_tunnel_context(tunnel_name)` to create namespace
4. Get namespace from returned metadata
5. **NEW:** Call `await self.routing.move_device_to_namespace(device, namespace)` to move device into namespace
6. **NEW:** Call `await self.routing.configure_namespace_network(namespace, device, vpn_ip, gateway, dns)` to configure address, route, DNS
7. Track tunnel in `adapter.tunnels` (already done)
8. Return response:
```python
{
    "msg_type": "allocated",
    "tunnel_name": tunnel_name,
    "namespace": namespace,
    "device": device,
    "gateway": gateway,
    "dns": dns,
    "vpn_ip": vpn_ip
}
```

**Acceptance criteria:**
- `src/daemon/resource_allocator.py` `_handle_allocate` extracts and validates `device`, `gateway`, `dns`, `vpn_ip`
- After namespace creation, calls `move_device_to_namespace()` and `configure_namespace_network()`
- Returns full metadata in response
- Errors: Missing fields → `{"msg_type": "error", "error": "Missing <field>"}`; move/configure failures → log and attempt namespace cleanup, return error
- Test: Unit test confirms allocate flow calls move_device_to_namespace with correct args

---

### Task 1.3: Ensure NetworkNamespaceRouting has required methods

**Read first:**
- `src/libvpnmanager/routing/namespace.py` (existing methods)

**Action:**
Verify the following methods exist and work correctly:
- `create_tunnel_context(tunnel_name)` – creates namespace, returns metadata (exists ✓)
- `move_device_to_namespace(device, namespace)` – moves device into namespace (exists ✓)
- `configure_namespace_network(namespace, device, vpn_ip, gateway, dns)` – configures address, route, DNS (exists ✓ as `configure_namespace_network`)

If any method is missing or incomplete, implement/complete it according to spec:
- `move_device_to_namespace`: executes `ip link set <device> netns <namespace>`; raises `DeviceNotFoundError` or `NamespaceNotFoundError` as appropriate
- `configure_namespace_network`: brings up loopback, sets device IP (/32), sets default route via gateway, configures DNS via resolv.conf copy

**Acceptance criteria:**
- All three methods present and functional
- They use `_run_command` / `_run_command_in_ns` to execute ip commands
- They raise appropriate exceptions on failure
- Test: Unit test with mocked subprocess verifies correct command sequences

---

### Task 1.4: Write integration test for full AllocateTunnel flow

**Read first:**
- Existing integration tests in `.planning/phases/02-proton-adapter-cli-integration/` (test structure)
- `tests/integration/test_resource_allocation.py` (if exists) or create new

**Action:**
Create or extend integration test: `tests/integration/test_phase3_allocation.py`
Test scenario:
1. Start MTM daemon (with test configuration)
2. Start a test adapter (dummy adapter is sufficient) that sends AllocateTunnel with device, gateway, dns, vpn_ip
3. Verify response contains namespace, device, gateway, dns, vpn_ip
4. Verify namespace exists: `ip netns list` includes `vpn_<tunnel_name>`
5. Verify device is in namespace: `ip netns exec vpn_<tunnel_name> ip link show <device>` shows device as UP
6. Verify route: `ip netns exec vpn_<tunnel_name> ip route` shows default via gateway
7. Verify DNS: `ip netns exec vpn_<tunnel_name> cat /etc/resolv.conf` contains DNS servers
8. Call ReleaseTunnel and verify namespace is deleted

Use pytest-asyncio and test fixtures. Mock subprocess if needed for CI environments without NET_ADMIN.

**Acceptance criteria:**
- Test file exists and passes (can run with `pytest -q tests/integration/test_phase3_allocation.py`)
- Test covers happy path: allocation configures namespace correctly with device and network
- Test covers cleanup: ReleaseTunnel deletes namespace

---

### Task 1.5: Verify DAEM-03 and DAEM-04 are satisfied

**Read first:**
- `.planning/REQUIREMENTS.md` definitions for DAEM-03 and DAEM-04

**Action:**
Manual verification checklist:
- **DAEM-03**: "MTM AllocateTunnel handler creates network namespace (ip netns add), moves device into namespace (ip link set), configures address, routes, and DNS"
  - AllocateTunnel now includes device movement and network configuration ✓
  - Code path exercised in integration test ✓
- **DAEM-04**: "MTM ReleaseTunnel handler deletes namespace and cleans up associated resources"
  - ReleaseTunnel calls `destroy_tunnel_context()` which deletes namespace ✓
  - Cleanup verified in integration test ✓

Commit with message:
```
feat(phase-03): integrate full resource allocation with device movement and network configuration

AllocateTunnel now:
- Accepts device, gateway, dns, vpn_ip from adapter
- Moves device into namespace using ip link set
- Configures namespace network: loopback, device IP (/32), default route, DNS
- Returns complete metadata

ReleaseTunnel deletes namespace. Integration tests verify end-to-end flow.
```

**Acceptance criteria:**
- All tasks in Plan 01 complete and committed
- Integration test passes
- REQUIREMENTS.md can be updated to reflect DAEM-03/DAEM-04 validation (later in verification phase)

---

## Plan 02: Configurable Idle Timeout + Test Coverage

**Objective:** Make adapter idle timeout configurable; add unit/integration tests for Phase 3 features (crash recovery, idle timeout); run regression tests from prior phases.

**Wave:** 2 (depends on Plan 01 complete)
**Depends on:** Plan 01
**Files modified:**
- `src/daemon/adapter_registry.py` – Configurable idle timeout
- `tests/unit/test_adapter_registry.py` – Idle timeout, crash cleanup tests
- `tests/integration/test_phase3_crash_idle.py` – Crash recovery and idle shutdown
- Possibly `.planning/phases/03-*/03-VERIFICATION.md` (auto-generated)

**Tasks:**

### Task 2.1: Make idle timeout configurable

**Read first:**
- `src/daemon/adapter_registry.py` (current _idle_timeout = 300.0)
- `.planning/config.json` (existing configuration structure)

**Action:**
1. In `AdapterRegistry.__init__`, accept optional `idle_timeout` parameter (float, seconds). Default to 300.0 if not provided.
2. Add setter method: `set_idle_timeout(seconds: float)` for runtime updates if needed
3. Update `VPNDaemon.__init__` to read idle timeout from config (e.g., `config.get("idle_timeout", 300)`) and pass to `AdapterRegistry`
4. Add config documentation: config key `daemon.idle_timeout` or `adapter.idle_timeout` in `.planning/config.json` or system config file

**Acceptance criteria:**
- `AdapterRegistry.__init__(..., idle_timeout: float = 300.0)` stores `self._idle_timeout`
- `VPNDaemon` reads config and passes value
- Can adjust timeout via config without code changes
- Test: Create registry with custom timeout, verify `_cleanup_loop` uses that value

---

### Task 2.2: Write unit test for crash recovery (DAEM-05)

**Read first:**
- `src/daemon/adapter_registry.py` `_unregister_by_pid` and `release_adapter_tunnels`
- `src/daemon/resource_allocator.py` `release_adapter_tunnels`

**Action:**
Create `tests/unit/test_adapter_registry_crash.py`:
- Mock `AdapterInstance` with `.tunnels = {"tunnel1", "tunnel2"}` and `.session_id`, `.username`
- Mock `ResourceAllocator` with async `release_adapter_tunnels` method (use MagicMock)
- Call `await registry._unregister_by_pid(pid)` after registering the mock adapter
- Assert `resource_allocator.release_adapter_tunnels` was called with the adapter instance
- Assert adapter removed from `registry._by_pid` and `registry.adapters`

**Acceptance criteria:**
- Unit test covers crash cleanup trigger
- Uses pytest-asyncio; passes with `pytest -q tests/unit/test_adapter_registry_crash.py`

---

### Task 2.3: Write unit test for idle timeout (DAEM-06)

**Read first:**
- `AdapterRegistry._cleanup_loop` implementation

**Action:**
Create `tests/unit/test_adapter_registry_idle.py`:
- Create `AdapterRegistry` with `idle_timeout=10` seconds
- Register mock adapter with `last_used` set to `time.time() - 20` (older than timeout)
- Start cleanup task (`await registry.start_cleanup_task()`)
- Advance time (or mock `asyncio.sleep` and `time.time()` if possible) to trigger cleanup
- Or manually invoke one iteration of the cleanup logic (extract into testable method)
- Verify `terminate_adapter` was called for the idle adapter
- Also test: adapter with recent `last_used` is NOT terminated

**Acceptance criteria:**
- Unit test verifies idle detection and termination
- Test passes

---

### Task 2.4: Write integration test for crash recovery (DAEM-05)

**Read first:**
- Phase 2 integration test structure
- Dummy adapter implementation

**Action:**
Create `tests/integration/test_phase3_crash_recovery.py`:
1. Start MTM daemon
2. Start dummy adapter (from Phase 1) and create a tunnel (causes AllocateTunnel)
3. Verify namespace exists for the tunnel
4. Simulate adapter crash: send SIGKILL to adapter process
5. Wait for `_unregister_by_pid` to fire (check logs or state)
6. Verify namespace for that tunnel is deleted (`ip netns list` does not show it)
7. Verify adapter removed from `adapter_registry.list_adapters()`

**Acceptance criteria:**
- Integration test demonstrates crash cleanup in action
- Passes end-to-end

---

### Task 2.5: Run regression tests for Phase 1 and Phase 2

**Read first:**
- `tests/integration/` for Phase 1 and Phase 2 test suites
- `.planning/phases/01-foundation/01-SUMMARY.md` and `02-proton-adapter-cli-integration/02-SUMMARY.md` for test coverage

**Action:**
1. Ensure Phase 3 changes do not break existing tests:
   ```
   pytest -q tests/integration/test_phase1_*.py
   pytest -q tests/integration/test_phase2_*.py
   ```
2. If tests mock external dependencies (proton.vpn.core.api), ensure mocks still work
3. Fix any regressions before moving to verification

**Acceptance criteria:**
- All prior-phase integration tests pass
- No broken backward compatibility

---

### Task 2.6: Commit and prepare for verification

**Read first:**
- STATE.md, ROADMAP.md for project conventions

**Action:**
Commit all changes with clear messages:
```
feat(phase-03): configurable adapter idle timeout

- Add idle_timeout parameter to AdapterRegistry
- Read from daemon config with default 300s
- Add set_idle_timeout for runtime updates

test(phase-03): add unit tests for registry

- test_adapter_registry_crash.py verifies crash cleanup
- test_adapter_registry_idle.py verifies idle termination
- test_phase3_allocation.py integration: full AllocateTunnel flow
- test_phase3_crash_recovery.py integration: crash cleanup

fix(phase-03): AllocateTunnel performs device movement and network config
```

Create SUMMARY.md for Plan 02 with summary of changes and testing results.

**Acceptance criteria:**
- All Phase 3 tasks committed with atomic commits
- `03-SUMMARY.md` exists and documents what was built
- Tests pass locally (can be run)

---

## Quality Gates & Verification

### Deep Work Rules Compliance

Every task above includes:
- `<read_first>` specifying files to read before modification
- `<acceptance_criteria>` with verifiable conditions (grep, file existence, test commands)
- `<action>` with concrete value specifications (default 300.0, config key names)

### Dependencies

- Plan 02 depends on Plan 01 (AllocateTunnel integration must be complete before tests can cover it)
- Phase 2 must be complete (adapter sends proper AllocateTunnel payload)

### must_haves for Phase Goal

The plan must deliver to satisfy Phase 3 success criteria:
1. **Namespace allocation on tunnel create** → Task 1.2 (AllocateTunnel handler) + Task 1.3 (routing methods) + Task 1.1 (adapter sends fields)
2. **Cleanup on destroy** → Already implemented? Check ReleaseTunnel path; Task 1.2 updates it if needed
3. **Crash recovery** → Already implemented in adapter_registry (daemon/02) + Task 2.2/2.4 (tests)
4. **Idle shutdown** → Already implemented with hardcoded timeout + Task 2.1 (configurable) + Task 2.3 (test)

---

## Implementation Notes

### AllocateTunnel Protocol Extension

The existing `_handle_allocate` returns only `{"namespace": ns_name}`. This plan extends it to:
- Accept: `device`, `gateway`, `dns`, `vpn_ip`
- Perform: `move_device_to_namespace(device, namespace)` and `configure_namespace_network(namespace, device, vpn_ip, gateway, dns)`
- Return: `{"namespace": ns_name, "device": device, "gateway": gateway, "dns": dns, "vpn_ip": vpn_ip}`

Adapter will need to parse this response and update its Tunnel object accordingly (namespace is already extracted; additionally store gateway/dns if needed).

### Idle Timeout Config Path

Suggested config hierarchy (to be implemented in Task 2.1):
- Read from `VPNDaemon` config dict: `config.get("idle_timeout", 300)`
- Allow environment variable override: `MTM_IDLE_TIMEOUT` (lower priority than config file, higher than default)
- Store in `AdapterRegistry._idle_timeout` as float seconds

### Test Strategy

- Unit tests: use `pytest-asyncio`, `unittest.mock` for subprocess and asyncio tasks
- Integration tests: require root privileges (CAP_NET_ADMIN) or use `unshare`; if CI lacks, mark with `pytest.mark.root_required` or skip

---

## Success Criteria

After executing both plans:
- ✓ AllocateTunnel creates namespace, moves device, configures network (verified by integration test)
- ✓ ReleaseTunnel deletes namespace (verified by integration test)
- ✓ Adapter crash triggers automatic cleanup of its tunnels (verified by unit + integration tests)
- ✓ Idle timeout is configurable and works (verified by unit test)
- ✓ No regression in Phase 1 or Phase 2 functionality
- ✓ All tests pass

Phase verification (`/gsd:verify-work 3`) will run automated checks and request any remaining human verification (e.g., manual namespace validation on real system).

---

End of PLAN.md
