# Proton VPN CLI: Multi-Tunnel Adapter Architecture

## What This Is

A major rearchitecture of the Proton VPN CLI's Multi-Tunnel Manager (MTM) to use **persistent adapter processes** with **direct CLI-to-adapter communication**. The system transforms from a monolithic daemon that directly manages adapters into a **process supervisor** where:

- Adapters run as persistent processes (one per user per adapter type)
- Credentials live only in adapter memory (no disk storage)
- CLI talks directly to adapters after startup
- MTM acts as adapter manager + namespace allocator (not message relay)
- Two-channel architecture: CLI↔Adapter (tunnel ops), Adapter↔MTM (resource allocation)

**Status:** In-progress implementation based on detailed specification document.

---

## Core Value

Transform MTM from a monolithic daemon into a **process supervisor with privileged network management**, moving VPN protocol logic into isolated, credential-holding adapter processes. This delivers:

- ✅ **No credential persistence** — better privacy, no plaintext tokens on disk
- ✅ **Simpler session model** — one adapter = one user session (single login)
- ✅ **Adapter reuse** — second tunnel uses same adapter (credentials reused)
- ✅ **Multi-tunnel without special connector** — multiple connections from same VPN session
- ✅ **Cleaner separation** — MTM only does privileged ops; adapters do protocol logic
- ✅ **Better failure isolation** — Adapter crash only affects that user's tunnels
- ✅ **Easier debugging** — Each adapter is separate process with independent logs

If anything fails, the **single most important thing** is: secure multi-tunnel VPN management without credential persistence on disk.

---

## Requirements

### Validated

*(None yet — existing codebase has partial implementation of current architecture, not the target architecture)*

### Active

- [ ] **ARCH-01**: MTM daemon can spawn and manage persistent adapter processes with two Unix sockets (CLI endpoint + control endpoint)
- [ ] **ARCH-02**: Adapters accept credentials via stdin on startup (not environment variables) and store them only in process memory
- [ ] **ARCH-03**: CLI can discover running adapters and their endpoints via MTM `StartAdapter()` / `ListAdapters()` D-Bus methods
- [ ] **ARCH-04**: CLI connects directly to adapter Unix socket for tunnel operations (create, destroy, connect, disconnect, status)
- [ ] **ARCH-05**: CLI → Adapter → MTM control channel implements namespace allocation during tunnel creation (AllocateTunnel, ReleaseTunnel)
- [ ] **ARCH-06**: MTM implements network namespace creation and device migration using pyroute2/ip commands
- [ ] **ARCH-07**: Adapters track multiple tunnels simultaneously in a single process (tunnels dictionary)
- [ ] **ARCH-08**: MTM detects adapter process crashes and cleans up associated namespaces and tunnels
- [ ] **ARCH-09**: Legacy D-Bus tunnel API continues to work alongside new direct adapter API (backward compatibility)
- [ ] **ARCH-10**: Adapter CLI subcommands provide user control (protonvpn adapter list, stop)
- [ ] **ARCH-11**: Credential prompts appear only when adapter requires login and no running instance exists
- [ ] **ARCH-12**: Unit and integration tests cover new adapter lifecycle, dual-channel communication, and namespace allocation

### Out of Scope

- [ ] **New VPN protocols** — Only the Proton adapter is migrated; other adapters (Psiphon, WireGuard) remain unimplemented or use old architecture
- [ ] **Cross-platform support** — Linux network namespaces are Linux-specific; no Windows/macOS support in this rearchitecture
- [ ] **GUI/Desktop integration** — CLI-only changes; desktop app uses same APIs but not part of this project
- [ ] **Session persistence** — Explicitly removed; no disk storage of credentials or sessions; users must re-login after adapter restart
- [ ] **Distributed MTM** — No clustering or multi-host daemon support; single-machine only
- [ ] **Real-time adapter auto-scaling** — No dynamic adapter spawning based on load; adapters per user per type only

---

## Context

This is a **brownfield rearchitecture** of an existing codebase. The current implementation:

- `multi-tunnel-namespace/src/` contains the working code under active development
- `docs/NEW_ADAPTER_ARCHITECTURE_SPECIFICATION.md` provides the complete design spec (March 2025)
- Existing code already exhibits many target patterns: adapter registry, resource allocator, dual Unix sockets, namespace handling
- Migration is incremental: legacy D-Bus API preserved alongside new direct adapter API

**Key architectural insight:** The shift is from **in-process adapter calls** to **inter-process adapter communication**, fundamentally changing the concurrency model, state management, and security boundaries.

**Dependencies:**
- Python 3.9+ with asyncio
- D-Bus for daemon IPC (already used)
- Linux network namespaces and pyroute2
-Unix socket permissions model (0600, user isolation)

**Related work:** See `.planning/codebase/ARCHITECTURE.md` for current state analysis.

---

## Constraints

- **Backward compatibility** — Existing CLI tools and scripts using legacy MTM D-Bus API must continue working unchanged during transition period.
- **Linux-only** — Network namespace operations are Linux-specific; this rearchitecture assumes Linux kernel features (ip netns, veth pairs).
- **Incremental migration** — Cannot break current working multi-tunnel setups; must support side-by-side old and new code paths.
- **No credential disk exposure** — Even temporary disk writes of credentials are forbidden; stdin or ephemeral memory only.
- **Process supervision** — MTM must reliably monitor adapter health and clean up resources on crash/exit.

---

## Current Milestone: v2.0 — Node.js Rewrite

**Goal:** Rewrite the multi-tunnel VPN manager from Python to Node.js, removing all Python code while preserving the dual-socket adapter architecture and control protocol. The rewrite targets Linux x86_64 and Windows 11 initially, with OS abstraction for portability and binary compilation for distribution.

**Target features:**
- Node.js daemon (MTM) with same responsibilities: adapter lifecycle, namespace allocation, crash cleanup
- Adapter base class and dummy adapter in Node.js
- Client library (ManagerClient, AdapterClient) in Node.js
- OS-abstracted IPC layer (no D-Bus; use cross-platform local sockets/streams)
- Process supervision and signal handling for both Linux and Windows
- Binary packaging for x86_64 Linux and Windows 11 (via pkg/nexe or similar)
- Integration tests for end-to-end adapter flow

**Out of scope for v2.0:**
- Full feature parity with all Proton VPN protocol details (dummy adapter demonstrates architecture)
- Windows network namespace simulation (Linux namespaces remain Linux-only)
- Migration of existing Python test suite (new tests in Node.js)

---

## Key Decisions

| Decision | Rationale | Outcome |
|----------|-----------|---------|
| **Credentials via stdin** | Avoids `/proc/<pid>/environ` exposure; simple one-time delivery | Implemented in spec Step 4; adapter reads once on startup |
| **Adapter pooling key: (type, username)** | One login per user session; reuse across tunnels | Shared adapter process for all tunnels of same type by same user |
| **Dual Unix sockets** | Separate CLI traffic from control messages; clear boundary | `ADAPTER_ENDPOINT` for CLI, `CONTROL_ENDPOINT` for MTM control |
| **Legacy API preserved** | Avoid breaking existing users; gradual migration | Old D-Bus create_tunnel route forwards internally to new adapter |
| **No session recovery** | Simpler model; credentials in memory only; restart fresh | After MTM or adapter restart, users must re-login |
| **Inherit model profile** | Use current session model for all agents (quality varies) | Reduces cognitive load; consistent with user's workflow |
| **Node.js rewrite** | Cross-platform potential, single runtime, binary packaging ecosystem | All Python code replaced; new IPC layer; OS abstraction for sockets, processes, signals |

---

*Last updated: 2025-03-20 after initial project bootstrapping*
