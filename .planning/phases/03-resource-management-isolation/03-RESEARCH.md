# Phase 3: Resource Management & Isolation — Research

**Gathered:** 2026-03-20 (manual research due to agent credits limitation)
**Status:** Planning ready — gaps identified

---

## What Already Exists

The codebase already has substantial Phase 3 infrastructure implemented:

### ✅ Namespace Creation & Cleanup (DAEM-03, DAEM-04)

**Location:** `src/libvpnmanager/routing/namespace.py`

- `NetworkNamespaceRouting.create_tunnel_context()` creates namespace `vpn_{tunnel_name}` via `ip netns add`
- `destroy_tunnel_context()` deletes namespace with `ip netns delete`
- `move_device_to_namespace()` moves devices into namespace using `ip link set <dev> netns <ns>`
- `configure_namespace_network()` configures:
  - Loopback up
  - TUN device IP address (`/32`)
  - Default route via gateway
  - DNS via `resolv.conf` copy
- Thread-safe with `asyncio.Lock`

### ✅ Control Protocol Handlers (DAEM-03, DAEM-04)

**Location:** `src/daemon/resource_allocator.py`

- `ResourceAllocator` runs internal Unix socket (`/run/mtm/internal.sock`)
- Handlers:
  - `_handle_allocate()` → calls `routing.create_tunnel_context()`, tracks in `adapter.tunnels`
  - `_handle_release()` → calls `routing.destroy_tunnel_context()`, removes from `adapter.tunnels`
- Authentication via `SO_PEERCRED` to accept only MTM-spawned adapters
- Length-prefixed JSON protocol (4-byte header)

### ✅ Crash Detection & Cleanup (DAEM-05)

**Location:** `src/daemon/adapter_registry.py`

- `AdapterRegistry._wait_for_process()` awaits `process.wait()` for each adapter
- On exit: `_unregister_by_pid()` automatically invokes `resource_allocator.release_adapter_tunnels(adapter)` if adapter had tunnels
- Bidirectional registry-allocator linking:
  - `adapter_registry.set_resource_allocator()`
  - `resource_allocator.set_adapter_registry()`

### ✅ Idle Timeout (DAEM-06)

**Location:** `src/daemon/adapter_registry.py`

- Background task `_cleanup_loop()` runs every 60 seconds
- Checks `last_used` timestamp on all adapters
- Terminates adapters idle > `_idle_timeout` (default **300 seconds / 5 minutes**)
- `terminate_adapter()` cleanly stops process and removes socket
- **Configurable?** Currently hardcoded; may need setter method or config integration

---

## Gaps & Open Questions

### 1. AllocateTunnel Incomplete – Device Movement Not Integrated

**Current behavior:**
- `ResourceAllocator._handle_allocate()` only creates namespace and returns `{"namespace": ns_name}`
- It does **not**:
  - Accept `device`, `gateway`, `dns` from adapter
  - Move device into namespace
  - Configure network address, routes, or DNS

**Required for DAEM-03:**
- Adapter sends `AllocateTunnel` with `tunnel_name`, `device`, `gateway`, `dns` (or MTM retrieves device from adapter separately)
- MTM moves device into namespace and configures network stack
- MTM returns full metadata including namespace, device, gateway, dns

**Implementation options:**

**Option A – Allocate includes device info**
```python
# Adapter request
{
  "msg_type": "allocate",
  "tunnel_name": "work",
  "device": "tun0",
  "gateway": "10.8.0.1",
  "dns": ["1.1.1.1", "1.0.0.1"]
}
# MTM response
{
  "msg_type": "allocated",
  "namespace": "vpn_work",
  "device": "tun0",
  "gateway": "10.8.0.1",
  "dns": ["1.1.1.1", "1.0.0.1"]
}
```

**Option B – Two-phase: Allocate then Configure**
1. `AllocateTunnel(tunnel_name)` → returns namespace
2. Adapter configures device on its own (sets up TUN, gets assigned IP)
3. Adapter sends `ConfigureTunnel` with device, gateway, DNS → MTM moves device and configures namespace

**Option C – MTM pulls device info from adapter**
- MTM calls back to adapter via control socket to query device info after allocation

**Recommendation:** **Option A** (single request) is simplest and matches spec wording: "AllocateTunnel(tunnel_name, device, gateway, dns) results in namespace with device moved inside". This keeps the protocol symmetric and avoids extra roundtrips.

**Tasks to close gap:**
1. Update `_handle_allocate()` to accept `device`, `gateway`, `dns` (validate required fields)
2. Call `self.routing.move_device_to_namespace(device, namespace)` **after** namespace creation
3. Call `self.routing.configure_namespace_network(namespace, device, vpn_ip, gateway, dns)` with IP from adapter's config
4. Return complete metadata including `device`, `gateway`, `dns` in response
5. Handle errors: device not found, move failure → release namespace to avoid leaks

**Edge case:** Device movement requires `CAP_NET_ADMIN` in init namespace; MTM runs as root so should have it. Verify `ip link set netns` succeeds.

---

### 2. DNS Configuration Scope

**Current:** `configure_namespace_network()` writes `/etc/resolv.conf` inside namespace.

**Missing for completeness:**
- `systemd-resolved` integration (if system uses it)
- Handling of `resolv.conf` symlinks
- Validation that DNS is actually used by processes in namespace

**Ser:** For MVP, direct `resolv.conf` write is sufficient. Can enhance later if needed.

---

### 3. Idle Timeout Configuration (DAEM-06)

**Current:** `AdapterRegistry._idle_timeout = 300.0` (hardcoded)

**Need:** Make configurable via:
- Config file (`/etc/mtm/config.toml` or similar)
- Environment variable (`MTM_IDLE_TIMEOUT=600`)
- D-Bus property (for runtime adjustment)

**Tasks:**
- Add `set_idle_timeout(seconds)` method to `AdapterRegistry`
- Read from config in `__init__` with fallback to default
- Document configuration option

---

### 4. AllocateTunnel Should Validate Tunnel Uniqueness

**Current:** `create_tunnel_context()` raises `NamespaceExistsError` if namespace already exists.

**MTM should also track** that a single adapter can have multiple tunnels (adapter.tunnels set already does this). Need to ensure:
- Same adapter can `AllocateTunnel` multiple times with different tunnel names
- ReleaseTunnel only removes that specific tunnel

**Already handled?** Yes:
- `adapter.tunnels` is a set; add/remove on allocate/release
- `release_adapter_tunnels()` iterates all tunnels for crashed adapter

---

### 5. Testing Gaps (TST-02, TST-03)

**Phase 4 testing requirements:**
- **TST-02**: Crash recovery test – simulate adapter crash, verify namespace cleanup
- **TST-03**: Concurrent connections – multiple CLI to same adapter

**Phase 3 should have:** Unit/integration tests for:
- `ResourceAllocator._handle_allocate()` → namespace created, device moved, network configured
- `ResourceAllocator._handle_release()` → namespace deleted
- `AdapterRegistry._unregister_by_pid()` → triggers `release_adapter_tunnels()`
- Idle timeout → adapter terminated after no tunnels

**Current state:** Integration tests from Phase 2 are stubs pending Proton core mock. The test infrastructure exists but needs bodies filled.

---

## Dependency Chain

```
Phase 2 complete → Phase 3 planning → Phase 3 execution
     ↓
Need PLAN.md for Phase 3
     ↓
Identify tasks addressing gaps above:
1. Integrate device movement & network config into AllocateTunnel
2. Make idle timeout configurable
3. Write tests for resource allocation
4. Run regression tests from Phase 1/2
5. Verify Phase 3 success criteria
```

---

## Success Criteria Verification Plan

| Criterion | Implementation | Test Approach |
|-----------|----------------|---------------|
| Namespace allocation on tunnel create | AllocateTunnel handler calls `create_tunnel_context()`, `move_device_to_namespace()`, `configure_namespace_network()` | Integration test: send Allocate msg, verify namespace exists, device in ns, route configured, DNS present |
| Cleanup on destroy | ReleaseTunnel handler calls `destroy_tunnel_context()` | Integration test: Allocate then Release, verify namespace gone |
| Crash recovery | `AdapterRegistry._unregister_by_pid()` → `release_adapter_tunnels()` | Unit test: mock adapter with .tunnels set, call `_unregister_by_pid`, assert destroy called for each tunnel |
| Idle shutdown | `_cleanup_loop()` checks `last_used`, calls `terminate_adapter()` | Unit test: set adapter.last_used to old timestamp, run cleanup iteration, verify terminate called |

---

## Recommendation

**Phase 3 scope is mostly implemented** but **incomplete** for DAEM-03 (device movement/config). The planning phase should create 1–2 focused plans:

1. **Plan 01**: Integrate full resource allocation (device movement, network configuration) into `AllocateTunnel` handler
2. **Plan 02**: Configurable idle timeout and test coverage for Phase 3 flows

After planning, execute, then verify with `/gsd:verify-work 3`.

---

## References

- `src/daemon/daemon.py` – Daemon startup, registry/allocator wiring
- `src/daemon/adapter_registry.py` – Adapter lifecycle, crash detection, idle timeout
- `src/daemon/resource_allocator.py` – Control protocol, allocate/release handlers
- `src/libvpnmanager/routing/namespace.py` – Namespace operations, device movement, network config
- `.planning/phases/03-resource-management-isolation/03-CONTEXT.md` – Open decisions
