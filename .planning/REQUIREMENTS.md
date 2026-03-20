# Requirements: Proton VPN CLI Multi-Tunnel Adapter Architecture

**Defined:** 2025-03-20
**Core Value:** Transform MTM into a process supervisor with isolated, credential-holding adapter processes for secure multi-tunnel VPN management without disk credential persistence.

---

## v1 Requirements

### Daemon & Adapter Lifecycle

- [ ] **DAEM-01**: MTM daemon can spawn adapter processes as separate executables with two Unix socket endpoints (CLI socket for client connections, control socket for MTM control)
- [ ] **DAEM-02**: MTM tracks adapter processes by `(adapter_type, username)` key in `adapter_pool` and can `ListAdapters()` and `StopAdapter()` via D-Bus
- [ ] **DAEM-03**: MTM `AllocateTunnel` handler creates network namespace (`ip netns add`), moves device into namespace (`ip link set`), configures address, routes, and DNS
- [ ] **DAEM-04**: MTM `ReleaseTunnel` handler deletes namespace and cleans up associated resources
- [ ] **DAEM-05**: MTM monitors adapter process exit (via `asyncio.wait`) and on crash cleans up all tunnels belonging to that adapter
- [ ] **DAEM-06**: MTM implements idle timeout (configurable N minutes with no active tunnels) to gracefully shut down unused adapters

### Adapter Process & Communication

- [ ] **ADPT-01**: Adapter base class provides dual-server pattern: bind CLI Unix socket, connect to MTM control Unix socket, run both handlers concurrently
- [ ] **ADPT-02**: Control protocol: Adapter sends `Register` to MTM; MTM responds to `AllocateTunnel` with `{namespace, device}`; MTM handles `ReleaseTunnel`
- [ ] **ADPT-03**: Adapter reads credentials from **stdin** on startup (not environment variables) and clears buffer after reading
- [ ] **ADPT-04**: Adapter stores VPN session in process memory (globally accessible) and reuses it for multiple tunnel connections from same process
- [ ] **ADPT-05**: Adapter tracks multiple tunnels in `self.tunnels` dictionary; second tunnel uses same session without re-authentication
- [ ] **ADPT-06**: Adapter handles multiple concurrent CLI connections on its Unix socket using `asyncio.Lock` to protect shared state

### CLI Integration

- [ ] **CLI-01**: `ManagerClient.start_adapter(adapter_type, credentials)` method contacts MTM D-Bus, spawns adapter if needed, returns adapter endpoint
- [ ] **CLI-02**: `AdapterClient` connects to adapter Unix socket and sends JSON-RPC commands: `CreateTunnel`, `DestroyTunnel`, `ListTunnels`, `GetStatus`
- [ ] **CLI-03**: `protonvpn tunnel create` command uses new flow: call `start_adapter`, get endpoint, `AdapterClient.create_tunnel`, display results
- [ ] **CLI-04**: Interactive credential prompt appears only when adapter `requires_login=True` and no running adapter exists for that user/type
- [ ] **CLI-05**: New adapter subcommands: `protonvpn adapter list` shows running adapters; `protonvpn adapter stop <type>` stops adapter for current user

### Compatibility & Legacy Support

- [ ] **COMP-01**: Legacy D-Bus `CreateTunnel` / `ConnectTunnel` methods continue to work by internally calling `StartAdapter` and forwarding to adapter via control socket
- [ ] **COMP-02**: Old and new APIs can coexist; no breaking changes to existing scripts and tools

### Security

- [ ] **SEC-01**: Socket permissions: MTM creates adapter CLI socket with mode `0600`, owned appropriately; only requesting user can connect
- [ ] **SEC-02**: Credentials passed via stdin are not visible in `/proc/<pid>/environ`; adapter securely clears credential buffer after reading
- [ ] **SEC-03**: MTM control socket verifies peer credentials via `SO_PEERCRED` to prevent impersonation

### Testing & Quality

- [ ] **TST-01**: Integration test covers full flow: CLI → MTM.StartAdapter → adapter stdin → CLI→adapter → MTM control → namespace creation → tunnel connected
- [ ] **TST-02**: Crash and recovery test: simulate adapter crash during active tunnel, verify MTM detects and cleans namespace
- [ ] **TST-03**: Concurrent connection test: multiple CLI processes connect to same adapter simultaneously, create tunnels, verify isolation
- [ ] **TST-04**: Dummy adapter implementation exists for smoke testing without real Proton credentials

### Documentation

- [ ] **DOC-01**: Architecture documentation updated to reflect new adapter lifecycle and dual-channel communication
- [ ] **DOC-02**: Migration guide for users transitioning from old to new behavior (session persistence removed)
- [ ] **DOC-03**: Developer notes: adapter implementation guide, protocol specs, testing strategies

---

## v2 Requirements

*Deferred to future release; acknowledged but not in current roadmap.*

### Enhanced Adapter Management

- **ADPT-07**: Adapter auto-reconnect logic for expired VPN tokens (refresh with stored `refresh_token`)
- **ADPT-08**: Adapter emits signals for state changes (`TunnelStateChanged`, `SessionExpired`) to connected CLIs
- **DAEM-07**: MTM signals adapter lifecycle events to interested clients (AdapterStarted, AdapterStopped, AdapterCrashed)

### Additional Adapters

- **ADPT-09**: Migrate WireGuard adapter to new architecture
- **ADPT-10**: Migrate Psiphon adapter to new architecture

### Observability

- **OBS-01**: Structured logging from adapters and daemon (JSON logs, correlation IDs)
- **OBS-02**: Metrics collection: adapter process count, tunnel count, namespace creation latency
- **OBS-03**: Health check endpoint for MTM daemon (systemd, monitoring)

### Performance

- **PERF-01**: Adapter startup latency optimization: async login, pre-warm connections
- **PERF-02**: Connection pooling within adapter to reduce VPN reauthentication overhead

---

## Out of Scope

| Feature | Reason |
|---------|--------|
| Session persistence on disk | Explicitly removed; security boundary: credentials in memory only |
| Windows/macOS support | Network namespaces are Linux-specific; cross-platform out of scope for this rearchitecture |
| Additional VPN protocols beyond Proton | Phase 1 only; migrations for WireGuard/Psiphon deferred to v2 |
| Distributed MTM (multi-host) | Single-machine scope; clustering would require separate project |
| Real-time adapter auto-scaling | Fixed pool model: one adapter per user per type; no dynamic scaling based on load |
| GUI/Desktop app changes | CLI-focused; desktop app uses same APIs but UI work not included |
| Mobile client support | Different platforms (iOS/Android) out of scope |

---

## Traceability

*Updated during roadmap creation.*

| Requirement | Phase | Status |
|-------------|-------|--------|
| DAEM-01 | Phase 1 | Pending |
| DAEM-02 | Phase 1 | Pending |
| ADPT-01 | Phase 1 | Pending |
| ADPT-02 | Phase 1 | Pending |
| ADPT-03 | Phase 1 | Pending |
| ADPT-06 | Phase 1 | Pending |
| CLI-01 | Phase 1 | Pending |
| CLI-02 | Phase 1 | Pending |
| TST-04 | Phase 1 | Pending |
| ADPT-04 | Phase 2 | Pending |
| ADPT-05 | Phase 2 | Pending |
| CLI-03 | Phase 2 | Pending |
| CLI-04 | Phase 2 | Pending |
| CLI-05 | Phase 2 | Pending |
| DAEM-03 | Phase 3 | Pending |
| DAEM-04 | Phase 3 | Pending |
| DAEM-05 | Phase 3 | Pending |
| DAEM-06 | Phase 3 | Pending |
| COMP-01 | Phase 4 | Pending |
| COMP-02 | Phase 4 | Pending |
| SEC-01 | Phase 4 | Pending |
| SEC-02 | Phase 4 | Pending |
| SEC-03 | Phase 4 | Pending |
| TST-01 | Phase 4 | Pending |
| TST-02 | Phase 4 | Pending |
| TST-03 | Phase 4 | Pending |
| DOC-01 | Phase 4 | Pending |
| DOC-02 | Phase 4 | Pending |
| DOC-03 | Phase 4 | Pending |

**Coverage:**
- v1 requirements: 29 total
- Mapped to phases: 29
- Unmapped: 0 ✓

---

*Requirements defined: 2025-03-20*
*Last updated: 2025-03-20 after initial definition*
