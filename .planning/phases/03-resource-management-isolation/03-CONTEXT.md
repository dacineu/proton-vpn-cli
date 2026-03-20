---
phase: 03
type: context
---

# Phase 3: Resource Management & Isolation — Context

## Domain Boundary

This phase covers the MTM daemon's resource allocation system: network namespace creation, device migration, cleanup on tunnel destruction, adapter crash recovery, and adapter lifecycle management (idle shutdown).

**In scope:**
- `AllocateTunnel` and `ReleaseTunnel` control protocol handlers
- Namespace creation (`ip netns add`), veth pair setup, device movement
- DNS configuration in namespace (resolv.conf, systemd-resolved)
- Crash detection of adapter processes and automated cleanup of associated resources
- Adapter idle timeout and graceful shutdown
- Integration with existing routing strategy (which already expects namespace to be set on Tunnel)

**Out of scope:**
- Per-application routing (that's Phase 4 or later)
- IPv6 handling (defer to later)
- Advanced firewall rules (beyond basic isolation)
- Cross-machine clustering

## Implementation Decisions (To Be Made)

1. **Where does namespace allocation logic live?**
   - Option A: In `daemon/resource_allocator.py` (already exists from Phase 1? Check)
   - Option B: Directly in control message handler
   - Option C: Separate `Allocator` class with testable unit

2. **How does MTM learn the TUN device name and gateway?**
   - Adapter returns `device` in Tunnel object; does it also provide gateway/DNS?
   - Phase 1/2 adapters might not provide gateway; may need heuristics or assume default

3. **Idle timeout mechanism:**
   - Per-adapter timer reset on each tunnel creation/destruction
   - Configuration: default 5 minutes, overridable via config file or env?
   - Implementation: `asyncio.timeout` or background task checking `last_activity` timestamp

4. **Crash detection method:**
   - Already using `process.wait()` in adapter registry? Check implementation.
   - Need callback/notification when adapter exits to trigger cleanup of its tunnels.

5. **Ordering of cleanup on adapter crash:**
   - Adapter dies → MTM gets all tunnel names from adapter registry entry?
   - Should we have adapter periodically checkpoint its tunnel list?
   - Or MTM maintains mapping: adapter_instance → set of tunnel names (from Allocate calls)

## Existing Code Insights

- `daemon/daemon.py` has `adapter_registry` that tracks adapters by session_name, including `process` and `control_socket`.
- `AllocateTunnel` and `ReleaseTunnel` messages are already used by dummy adapter; but are they implemented in daemon? Check Phase 1 daemon control handler.
- `resource_allocator.py` may exist from earlier architecture; review its API.
- Tunnel model: `libvpnmanager/models/tunnel.py` has `namespace`, `device`, `endpoint`, `metadata`.
- Routing strategy: `libvpnmanager/routing/` may have code that applies namespace to network config.

**Action:** Read daemon's control socket server to see current message handling.

## Dependencies & Risks

- **Linux only**: Network namespace operations use `pyroute2` or `ip` command; ensure available.
- **Race conditions**: Adapter crash during tunnel create; ensure Allocate is atomic and cleanup handles partial states.
- **Permission**: Need NET_ADMIN capability for namespace creation; MTM must run as root (already required).
- **Testing**: Without real network, tests may need mocking of `pyroute2` or use of `unshare`? Integration tests should create real namespaces (lightweight) and verify with `ip netns list`.

## Questions for Discussion

1. Should namespace naming be `vpn_<tunnel_name>` or `vpn_<session_id>_<tunnel_name>`? Phase 1 used `vpn_<tunnel_name>`.
2. Should MTM track tunnel ownership per adapter, or does adapter fully own its tunnels?
3. What is the expected behavior when `ReleaseTunnel` is called for a non-existent namespace? Ignore or error?
4. How to handle adapter crash while tunnel is active? Should MTM proactively disconnect adapter first?
5. Should idle timeout be configurable? If so, where (config file, env, D-Bus property)?

## References

- Phase 1 specification: `docs/NEW_ADAPTER_ARCHITECTURE_SPECIFICATION.md`
- Phase 1 implementation summary: `.planning/phases/01-foundation/01-SUMMARY.md`
- Resource allocator design: `docs/ARCHITECTURE_RESTRUCTURE.md` (search for namespace)
