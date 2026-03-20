# Multi-Tunnel Options: Quick Reference

## Side-by-Side Comparison

| Aspect | Option 1: Network Namespaces | Option 2: Policy Routing |
|--------|----------------------------|------------------------|
| **Dir** | `multi-tunnel-namespace/` | `multi-tunnel-policy-routing/` |
| **Mechanism** | Separate network namespace per tunnel | fwmark + routing tables + cgroup |
| **User Command** | `protonvpn tunnel switch work` (new shell) | `protonvpn tunnel mark work` (stay in shell) |
| **TUN Devices** | One per namespace (isolated) | All in main namespace (visible) |
| **Routing** | Each ns has its own default route | Each tunnel has routing table + rule |
| **Marking** | Not needed (already in ns) | `iptables` marks packets from cgroup |
| **DNS** | Per-ns resolv.conf (clean) | Shared DNS (may leak, needs DoH/forwarder) |
| **Overhead** | 2-10 MB per tunnel | <100 KB per tunnel |
| **Debugging** | `nsenter -n <ns> ip addr` | Direct `ip addr`, `iptables` |
| **Complexity** | High (namespace lifecycle) | Medium (tables + iptables) |
| **Max Tunnels** | ~50-100 | ~200-250 |
| **Kernel Min** | 3.9 (netns) | 3.0 (multiple tables) |
| **Security** | Strong isolation | Weaker (shared stack) |
| **Implementation Time** | ~6 months | ~4 months |
| **Polkit Needs** | `CAP_NET_ADMIN` for netns | `CAP_NET_ADMIN` for route+iptables |
| **CLI Simplicity** | Needs `nsenter` binary | Just writes to cgroup file |
| **Systemd Integration** | `Type=simple` or `dbus` | `Type=simple` or `dbus` |

---

## Implementation Complexity Breakdown

### Phase 1: Core Library (Both ~4 weeks)
- **Common**: Models, Adapter ABC, Manager, D-Bus, tests
- **Differs**: `routing/namespace.py` (1000 loc) vs `routing/policy.py` (800 loc)
- **Winner**: Option 2 slightly simpler

### Phase 2: Daemon (Both ~4 weeks)
- **Common**: D-Bus service, Polkit, config, systemd
- **Differs**: Namespace cleanup vs cgroup cleanup
- **Winner**: Option 2 (no namespace lifecycle)

### Phase 3: CLI (Option 1: 3 weeks, Option 2: 2 weeks)
- **Option 1**: Need robust `switch` (detach+attach), `exec` with nsenter
- **Option 2**: `mark` just writes to file, simpler
- **Winner**: Option 2

### Phase 4: Testing (Both ~2 weeks)
- **Option 1**: Test namespaces, verify isolation
- **Option 2**: Test routing tables, iptables rules
- **Winner**: Tie (both need comprehensive tests)

### Phase 5: Packaging (Both ~2 weeks)
- **Identical**: Same structure
- **Winner**: Tie

**Total Time**:
- Option 1: ~15 weeks (3.75 months)
- Option 2: ~13 weeks (3.25 months)

**Difference**: Only 2 weeks. So complexity not big factor.

---

## Decision Matrix

Rate importance 1-5 (5 = critical):

| Requirement | Weight | Option 1 | Option 2 | Weighted Score O1 | Weighted Score O2 |
|-------------|--------|----------|----------|------------------|-------------------|
| Security/isolation | 5 | 5 (complete) | 3 (partial) | 25 | 15 |
| Performance overhead | 3 | 3 (moderate) | 5 (low) | 9 | 15 |
| Implementation ease | 4 | 3 (hard) | 5 (easy) | 12 | 20 |
| Debugging ease | 4 | 2 (hard) | 4 (easy) | 8 | 16 |
| DNS isolation | 5 | 5 (native) | 2 (needs work) | 25 | 10 |
| Max tunnels | 2 | 3 (50-100) | 3 (200+) | 6 | 6 |
| Compatibility | 3 | 3 (3.9+) | 4 (3.0+) | 9 | 12 |
| User experience | 4 | 4 (new shell) | 4 (cgroup) | 16 | 16 |
| CLI simplicity | 4 | 3 (nsenter) | 5 (cgroup file) | 12 | 20 |
| **Total** | - | - | - | **123** | **130** |

**Option 2 wins** on weighted scoring (130 vs 123). The main penalty is DNS isolation.

---

## DNS Solution for Option 2

**The challenge**: All tunnels share same `/etc/resolv.conf`, so DNS requests may leak.

**Solutions**:

1. **DoT/DoH per app** (recommended):
   - Configure Firefox/Chrome to use DNS-over-HTTPS with specific resolver
   - CLI wrapper sets `MOZ_DNS_REMOTE_HOSTS` or `--doh-server`
   - Simple, no daemon changes

2. **Per-tunnel dnsmasq**:
   - Daemon spawns `dnsmasq` instance per tunnel listening on 127.0.0.N
   - iptables REDIRECT udp 53 to 127.0.0.N for marked packets
   - Each dnsmasq uses upstream resolver corresponding to tunnel location
   - More complex but transparent to apps

3. **iptables DNAT to per-tunnel DNS server**:
   - Parse VPN config for DNS server IPs
   - `iptables -t nat -A OUTPUT -p udp --dport 53 -m mark --mark 0x3e9 -j DNAT --to 10.8.1.1:53`
   - Works if VPN provides DNS server; but what if app uses DoH?

4. **Use `systemd-resolved` with per-link DNS**:
   - Not really possible in main namespace (all links share same resolv.conf)
   - Would need separate network namespace anyway

**Recommended**: Document DNS limitation, suggest DoT/DoH for privacy-sensitive apps. Option 2 is not DNS-isolated by default but can be with per-tunnel dnsmasq if someone wants to implement it later.

---

## My Verdict

**If you must choose one**: **Option 2 (Policy Routing)**.

Why?
- ✅ Simpler, faster to implement
- ✅ Easier to debug (no nsenter gymnastics)
- ✅ Good enough for 90% of use cases
- ✅ Can be enhanced with per-tunnel dnsmasq later if needed
- ✅ More tunnels possible
- ✅ Lower memory footprint

**Only choose Option 1 if**:
- DNS isolation is non-negotiable
- You need to run apps that cannot be configured for DoH
- You want the strongest security/isolation guarantees
- You're okay with 2 extra weeks of work

---

## TL;DR Commands

### Option 1 (Namespaces)
```bash
protonvpn tunnel create work --country US
# Creates namespace vpn_work, TUN moved there
protonvpn tunnel switch work
# Starts new shell in that namespace (via nsenter)
firefox  # Isolated, separate resolv.conf
exit     # Back to default
```

### Option 2 (Policy Routing)
```bash
protonvpn tunnel create work --country US
# Creates cgroup, routing table 1001, fwmark 0x3e9
protonvpn tunnel mark work
# Writes $$ to cgroup.procs, marks all future packets
firefox  # Marked, routed via table 1001
protonvpn tunnel mark default
# Clear cgroup (or move back)
```

---

## Start Now

Pick an option, then:

```bash
# Read its TODO
less multi-tunnel-namespace/TODO_OPTION1.md  # OR
less multi-tunnel-policy-routing/TODO_OPTION2.md

# Begin Phase 0: PoC
cd multi-tunnel-namespace/  # or policy-routing
# Create PoC script (see Phase 0)
```

Both directories are ready with complete PLANNING documents. Nothing implemented yet.

---

**Question**: Which option will you implement?
