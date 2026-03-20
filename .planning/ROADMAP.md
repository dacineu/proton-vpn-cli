# Roadmap: Multi-Tunnel Adapter Architecture

**Granularity:** Coarse (4 phases)
**Requirements Coverage:** 29/29 v1 requirements mapped ✓

---

## Phase Overview

| Phase | Name | Goal | Requirements | Success Criteria |
|-------|------|------|--------------|------------------|
| 1 | Foundation: Adapter Lifecycle & Core Protocol | Establish fundamental adapter pattern with dual sockets and working Dummy adapter | DAEM-01, DAEM-02, ADPT-01, ADPT-02, ADPT-03, ADPT-06, CLI-01, CLI-02, TST-04, SEC-04, SEC-05, SEC-06, SEC-07 | 4 |
| 2 | Proton Adapter & CLI Integration | Migrate Proton adapter to new model; integrate CLI direct flow | ADPT-04, ADPT-05, CLI-03, CLI-04, CLI-05 | 3 |
| 3 | Resource Management & Isolation | Implement namespace allocation, cleanup, and adapter lifecycle management | DAEM-03, DAEM-04, DAEM-05, DAEM-06 | 4 |
| 4 | Polish, Security & Compatibility | Harden security, preserve legacy API, complete testing and docs | COMP-01, COMP-02, SEC-01, SEC-02, SEC-03, SEC-08, TST-01, TST-02, TST-03, DOC-01, DOC-02, DOC-03 | 4 |

**Total:** 4 phases | 34 requirements | 15 success criteria

---

## Phase Details

### Phase 1: Foundation — Adapter Lifecycle & Core Protocol

**Goal:** Establish the fundamental adapter process pattern with dual Unix sockets and control protocol; deliver a working Dummy adapter that demonstrates the basic flow without real VPN operations.

**Requirements:**
- DAEM-01, DAEM-02
- ADPT-01, ADPT-02, ADPT-03, ADPT-06
- CLI-01, CLI-02
- TST-04
- SEC-04, SEC-05, SEC-06, SEC-07 (CLI-level 2FA token infrastructure)

**Success Criteria:**

1. **Adapter startup works**: `ManagerClient.start_adapter("dummy", creds)` returns adapter endpoint; adapter process runs, binds CLI socket, connects to MTM control socket, and sends `Register`.
2. **Dummy tunnel creation**: `AdapterClient` connects to adapter, sends `CreateTunnel`, receives dummy tunnel response (`device: "dummy0"`, etc.) without touching real network.
3. **Concurrent connections**: Multiple simultaneous CLI connections to the same adapter handled correctly (asyncio lock protects `self.tunnels`).
4. **Token authentication works**: Phase 1 implements token infrastructure with dummy tokens; `StartAdapter` accepts and passes `session_token` to adapter; adapter validates `session_token` on CLI requests (full TOTP in Phase 4).

**Key Deliverables:**
- `daemon/daemon.py`: `AdapterProcess` class, `StartAdapter()` D-Bus method, `ListAdapters()`, basic adapter_pool tracking, session token handling
- `adapters/dummy/cli.py` (new): dual-server pattern, stdin credential reading, Register to MTM, dummy CreateTunnel handler, session token validation
- `libvpnmanager/client.py`: `start_adapter()`, `AdapterClient` with JSON-RPC, session token propagation
- Integration smoke test using Dummy adapter with token validation

---

### Phase 2: Proton Adapter & CLI Integration

**Goal:** Migrate the existing Proton VPN adapter to the new architecture; integrate the CLI tunnel commands to use direct adapter communication; implement credential prompt and adapter subcommands.

**Requirements:**
- ADPT-04, ADPT-05
- CLI-03, CLI-04, CLI-05

**Success Criteria:**

1. **Direct proton tunnel creation**: `protonvpn tunnel create personal --adapter proton --country US --protocol wireguard` prompts for credentials only on first tunnel, then creates adapter and tunnel via direct socket connection.
2. **Session reuse**: Second `protonvpn tunnel create work ...` uses same adapter (no credential prompt) and creates a second tunnel concurrently using the same VPN session.
3. **Adapter management**: `protonvpn adapter list` shows running adapters; `protonvpn adapter stop proton` cleanly stops the adapter.

**Key Deliverables:**
- `adapters/proton_vpn_adapter/cli.py` refactored: dual-server, stdin credentials, global session, multiple tunnel tracking
- `cli/tunnel.py` updated to use new flow
- New `cli/adapter.py` with list/stop commands
- Remove old in-process adapter usage from legacy paths (but preserve D-Bus API externally)

---

### Phase 3: Resource Management & Isolation

**Goal:** Implement namespace allocation and cleanup in MTM; ensure proper network isolation; add adapter lifecycle management (crash detection, idle timeout).

**Requirements:**
- DAEM-03, DAEM-04, DAEM-05, DAEM-06

**Success Criteria:**

1. **Namespace allocation on tunnel create**: Adapter → MTM `AllocateTunnel(tunnel_name, device, gateway, dns)` results in a new network namespace `vpn_<tunnel_name>` with device moved inside, address configured, and DNS set.
2. **Cleanup on destroy**: Calling `DestroyTunnel` causes adapter to disconnect, adapter → MTM `ReleaseTunnel`, and MTM deletes the namespace.
3. **Crash recovery**: Adapter process killed → MTM detects within seconds → MTM iterates adapter.tunnels and calls `ReleaseTunnel` for each → all namespaces cleaned.
4. **Idle shutdown**: Adapter with no tunnels for 5 minutes is automatically shut down (configurable), verified by `adapter list` and system process table.

**Key Deliverables:**
- `daemon/daemon.py` control socket handler: `AllocateTunnel`, `ReleaseTunnel`
- `daemon/resource_allocator.py` implements namespace creation/device migration/DNS (already exists, wire into control handler)
- Background task: monitor adapter processes via `process.wait()`, trigger cleanup on exit
- Configurable idle timeout with asyncio timer per adapter
- Tests: verify namespace existence after allocation, removal after release

---

### Phase 4: Polish, Security & Compatibility

**Goal:** Harden security boundaries, ensure full backward compatibility of legacy API, complete integration testing, and deliver documentation.

**Requirements:**
- COMP-01, COMP-02
- SEC-01, SEC-02, SEC-03
- TST-01, TST-02, TST-03
- DOC-01, DOC-02, DOC-03

**Success Criteria:**

1. **Security audit passes**:
   - Adapter CLI socket: `ls -l /run/mtm/adapters/*.sock` shows `srw-------` owned by appropriate user/group.
   - Running `ps e <adapter_pid>` does not show VPN credentials in environment.
   - Control socket accepts connections only from adapters spawned by MTM (peer UID matches).
2. **Legacy API works**: Old-style `protonvpn tunnel create` (without explicit adapter argument) still creates tunnels identically to new CLI via legacy D-Bus path that internally forwards to adapter.
3. **Test suite passes**: Integration tests cover full flow, crash recovery, and concurrent access; all assertions green.
4. **Documentation complete**: Users can read architecture overview, migration guide explaining session persistence removal, and developer adapter implementation guide.

**Key Deliverables:**
- Socket permission setup in MTM before spawning adapters
- Credential stdin handling validation (test that `/proc` doesn't expose)
- `SO_PEERCRED` verification on control socket accepts
- Legacy D-Bus `CreateTunnel` handler: if adapter not running, call `StartAdapter`, then forward request via control channel (transparent to caller)
- Integration test suite in `tests/integration/` covering TST-01, TST-02, TST-03
- Documentation in `docs/` and `README.md` updates

---

## Implementation Order

Recommended sequential execution:

1. **Phase 1** → validates core architecture with Dummy adapter
2. **Phase 2** → brings real Proton adapter online and updates CLI
3. **Phase 3** → adds namespace magic and reliability features
4. **Phase 4** → polishing for production use

---

*Roadmap created: 2025-03-20*
*Last updated: 2025-03-20 after roadmapper run*
