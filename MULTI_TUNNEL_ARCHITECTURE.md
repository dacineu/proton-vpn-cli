# Multi-Tunnel VPN Architecture: Two Approaches

## Overview

This repository contains **two independent design proposals** for adding multi-tunnel, per-application VPN routing to Proton VPN CLI (and other VPNs). Each approach is self-contained in its own directory with comprehensive planning documents.

---

## The Problem

Current Proton VPN CLI supports **only one active connection** that routes **all system traffic**. There is no way to:
- Have multiple VPN connections simultaneously (e.g., US + Japan)
- Route specific applications through specific VPN tunnels
- Isolate different work/personal contexts on the same machine

**Current workaround**: Use separate VMs or containers, which is heavyweight.

---

## The Vision

Enable users to:
```bash
# Create a work tunnel (US)
protonvpn tunnel create work --country US
protonvpn tunnel mark work
firefox  # All browser traffic goes through US

# In another terminal, create personal tunnel (Japan)
protonvpn tunnel create personal --country JP
protonvpn tunnel mark personal
telegram  # Goes through Japan

# Switch back to default (no VPN or different tunnel)
protonvpn tunnel mark default
```

**Key goals**:
1. Multiple concurrent VPN connections
2. Per-application or per-shell routing
3. Vendor-neutral (support Proton, Psiphon, WireGuard, etc.)
4. Clean separation: daemon (privileged) + CLI (user)
5. Extensible adapter architecture

---

## Two Approaches

### Option 1: Network Namespaces (Complete Isolation)

**Directory**: `multi-tunnel-namespace/`

**Mechanism**: Each tunnel runs in its own **network namespace** (Linux kernel feature). Namespaces have separate:
- Network interfaces
- Routing tables
- Firewall rules
- DNS resolution

**User experience**:
```bash
protonvpn tunnel create work --country US
protonvpn tunnel switch work  # Launches new shell in work namespace
firefox  # Running in work namespace, isolated
exit  # Back to default namespace
```

**Pros**:
- ✓ Complete isolation (no leaks possible)
- ✓ Each namespace can have its own DNS
- ✓ Strong security boundary
- ✓ Works with any application (no special marking needed)

**Cons**:
- ✗ More complex (namespace lifecycle)
- ✗ Higher memory overhead (~2-10 MB per namespace)
- ✗ Debugging requires `nsenter`
- ✗ Need to manage `/var/run/netns/` cleanup

**Use when**: You need bulletproof isolation, separate DNS, or are running untrusted apps.

---

### Option 2: Policy Routing (fwmark + cgroup) (Simpler)

**Directory**: `multi-tunnel-policy-routing/`

**Mechanism**: All tunnels in main namespace, but traffic is routed based on **fwmark** set by **cgroup**. Each tunnel gets:
- A routing table (e.g., table 1001)
- A cgroup for marking processes
- iptables rule to mark packets from that cgroup
- `ip rule` to route marked packets via corresponding table

**User experience**:
```bash
protonvpn tunnel create work --country US
protonvpn tunnel mark work  # Moves current shell to work cgroup
firefox  # All traffic marked, routed via work's table
protonvpn tunnel mark default  # Back to normal
```

**Pros**:
- ✓ Simpler implementation (no namespace management)
- ✓ Lower overhead (shared network stack)
- ✓ Easier debugging (all devices visible in main namespace)
- ✓ Works with any application (cgroup inheritance)

**Cons**:
- ⚠ DNS may leak (all apps use same resolver)
- ⚠ Need per-tunnel DNS forwarder or DoH
- ⚠ Weaker isolation (same network namespace)
- ⚠ iptables rules can conflict with existing rules

**Use when**: You want quick implementation, minimal overhead, and can accept DNS complexity.

---

## Comparison Table

| Feature | Namespaces (Option 1) | Policy Routing (Option 2) |
|---------|----------------------|--------------------------|
| **Isolation** | Complete (network stack) | Partial (routing only) |
| **Implementation Complexity** | High | Medium |
| **Memory Overhead** | ~2-10 MB per tunnel | ~100 KB per tunnel |
| **Debugging** | Hard (need nsenter) | Easy (direct tools) |
| **DNS Isolation** | Yes (per-ns resolv.conf) | No (shared, need workaround) |
| **Compatibility** | Kernel 3.9+ | Kernel 3.0+ (older) |
| **Max Tunnels** | ~50-100 | ~200-250 |
| **CLI Command Pattern** | `tunnel switch` (new shell) | `tunnel mark` (cgroup move) |
| **Per-Device Control** | Yes (each ns has own dev) | Yes (all devices visible) |
| **Firewall per Tunnel** | Yes (per-ns iptables) | Limited (shared netfilter) |
| **Migration from Current** | Moderate | Easy |

---

## Project Structure

Each option is a **standalone project** with identical structure but different routing implementation:

```
multi-tunnel-namespace/          # Option 1
├── TODO_OPTION1.md             # Comprehensive task list
├── docs/                       # Architecture docs
├── src/
│   ├── libvpnmanager/          # Core library
│   │   ├── routing/
│   │   │   ├── namespace.py   # NetworkNamespaceRouting
│   │   │   └── policy.py      # (empty or base)
│   │   └── ...
│   ├── daemon/                 # proton-vpn-manager
│   └── cli/                    # Enhanced protonvpn CLI
├── packaging/
│   ├── deb/
│   └── rpm/
└── tests/

multi-tunnel-policy-routing/    # Option 2
├── TODO_OPTION2.md             # Comprehensive task list
├── docs/
├── src/
│   ├── libvpnmanager/
│   │   ├── routing/
│   │   │   ├── namespace.py   # (empty or stub)
│   │   │   └── policy.py      # PolicyRouting
│   │   └── ...
│   ├── daemon/
│   └── cli/
└── packaging/
```

**Shared components** (could be extracted to separate repo):
- `Tunnel` dataclass
- `VPNAdapter` ABC
- `ConnectionConfig` types
- D-Bus interface definition
- CLI command structure

**Differing components**:
- `routing/` implementation
- Daemon Polkit rules (slightly different capabilities)
- CLI `switch`/`exec`/`mark` implementation details
- Test scenarios

---

## How to Proceed

### Step 1: Choose an Option

Read both `TODO_OPTION1.md` and `TODO_OPTION2.md`.

**Consider**:
- **Option 1** if you want maximum isolation and are Okay with complexity
- **Option 2** if you want faster implementation and simpler debugging

**My recommendation**: Start with **Option 2** (policy routing). It's 60% of the way there with 40% of the namespace complexity. You can always add namespace support later as an advanced feature.

### Step 2: Implement Phase 0

From the chosen TODO file:

1. Create PoC script to verify routing strategy works
2. Define formal API specs
3. Set up empty repository
4. Begin Phase 1: Core Library

### Step 3: Coordinate with Daemon Team

The daemon (`proton-vpn-api-core` / `proton-vpn-local-agent`) needs to:
- Support multiple concurrent connections (currently single)
- Allow moving TUN device to namespace or leaving in main
- Provide hook for adapter to get gateway IP
- Allow querying active TUN devices for a given adapter

**This is the biggest external dependency**. You may need to:
- Fork `proton-vpn-api-core` and add multi-tunnel support
- Submit PR upstream
- Or design adapter to work with single-tunnel limitation (multiple Proton accounts? Multiple daemon instances?)

### Step 4: Follow the TODO

Each TODO file is a **complete implementation plan** with:
- ✅ Clear tasks with checkboxes
- Estimated timelines
- Code examples
- Risks and mitigations
- Success criteria

Start at Phase 0 and work through sequentially.

---

## Integration with Existing proton-vpn-cli

The current `proton-vpn-cli` (v0.1.8) will be **updated** to use this new library:

1. Add `libvpnmanager` dependency
2. Modify `connect` to accept `--tunnel-name`
3. Add `protonvpn tunnel` command group
4. Maintain backward compatibility:
   - No `--tunnel-name` → single-tunnel mode (current behavior)
   - With `--tunnel-name` → multi-tunnel mode

**Version bump**: Would be 0.2.0 or 1.0.0 (major change)

---

## Testing Both Options

Before committing to one:

1. **Implement Phase 0 PoC** for each option (1 week each)
2. Compare:
   - Lines of code
   - Complexity
   - Performance
   - Reliability
   - User experience

3. **Choose** and proceed with full implementation

Could even implement **both** and let users select routing strategy at install:
```
Daemon configuration: /etc/protonvpn/manager.conf
[routing]
strategy = namespace  # or "policy"
```

---

## Alternative Considered (Rejected)

### Option 3: Application Proxy (SOCKS5 per tunnel)

Simpler but limited:
- Each tunnel runs local SOCKS5 proxy
- Apps must support proxy configuration
- DNS leaks likely
- UDP support problematic

**Why rejected**: Too application-dependent, many apps don't support proxies cleanly.

---

## Questions to Answer Before Starting

1. **Can `proton-vpn-api-core` support multiple connections?**
   - If not, we need to modify it or run multiple daemon instances (each with own TUN)
   - This is a **blocking dependency**

2. **Do we want to support Psiphon from day one?**
   - If yes, design adapters accordingly
   - If only Proton, can simplify some interfaces

3. **What's the target user base?**
   - If mostly Proton users, optimize for Proton's capabilities
   - If general VPN, ensure adapter flexbility

4. **What's the timeline?**
   - Option 1: ~6 months full-time
   - Option 2: ~4 months full-time
   - Parallel development of both PoCs: ~2 months

5. **Do we need to support existing Polkit rules?**
   - The current `protonvpn` daemon has its own Polkit rules
   - New daemon would need separate rules
   - Could we reuse existing local-agent's privileges?

---

## Next Actions

### Immediate (This Week)
- [ ] Discuss with team which option to pursue
- [ ] Get access to `proton-vpn-api-core` source to assess multi-tunnel feasibility
- [ ] Build PoC for chosen routing strategy (2-3 days)
- [ ] Document findings and decision

### Short-term (Next 2 Weeks)
- [ ] Set up library skeleton
- [ ] Implement `Tunnel` and `VPNAdapter` ABC
- [ ] Write first unit tests
- [ ] Begin daemon structure

### Long-term (3-6 Months)
- Complete implementation per TODO
- Submit pull requests to proton repos
- Package for distros
- Release as beta

---

## Resources

- **Linux network namespaces**: `man ip-netns`, `man setns`
- **Linux policy routing**: `man ip-rule`, `man ip-route`
- **cgroups v1 net_cls**: `Documentation/cgroup-v1/net_cls.txt` in kernel docs
- **iptables MARK**: `man iptables-extensions`
- **D-Bus specification**: https://dbus.freedesktop.org/doc/dbus-specification.html

---

## Conclusion

Two complete, independent plans await. Choose one, implement PoC to validate, then follow the comprehensive TODO list to build production-ready multi-tunnel VPN manager.

**Remember**: The hardest part is getting Proton daemon to support multiple tunnels. Start there.

---

**Created**: 2026-03-15
**Status**: Planning phase
**Decision Needed**: Which option to implement?
