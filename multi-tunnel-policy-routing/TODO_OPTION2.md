# Multi-Tunnel VPN with Policy Routing - TODO List

**Option 2: Policy Routing with fwmark/cgroup**
**Project**: `libvpnmanager` + `proton-vpn-manager` daemon
**Date**: 2026-03-15
**Architecture**: Application-independent, adapter pattern for multiple VPN types

---

## 📋 Project Overview

Build a reusable library and daemon that enables:
- Multiple concurrent VPN tunnels (Proton VPN, Psiphon, WireGuard, etc.)
- Per-application routing using **iptables fwmark + policy routing rules**
- All tunnels active simultaneously in main network namespace
- Vendor-neutral adapter architecture
- D-Bus control interface for CLI/GUI tools

**Key Advantage**: Simpler than network namespaces (no namespace management), easier debugging, lower memory overhead. All TUN devices visible in main namespace.

---

## 🎯 Phase 0: Foundation & Design (Week 1-2)

### Research & Specification
- [ ] **Study existing implementations**:
  - How strongSwan/openswan handle multiple tunnels
  - How `mwan3` (multi-WAN) uses policy routing
  - How Docker handles container networking without full namespaces
  - Linux kernel policy routing: `ip rule`, `ip route` tables, `fwmark`

- [ ] **Define API contracts**:
  - [ ] Write formal specification for `VPNAdapter` interface (Python abstract base class)
  - [ ] Define `Tunnel` dataclass with routing metadata (table ID, fwmark)
  - [ ] Design `ConnectionConfig` hierarchy (ProtonConfig, PsiphonConfig, etc.)
  - [ ] Specify D-Bus interface (method signatures, signals, error codes)

- [ ] **Determine system requirements**:
  - [ ] Kernel config: `CONFIG_IP_MULTIPLE_TABLES=y`, `CONFIG_NETFILTER_XT_TARGET_MARK=y`
  - [ ] Number of routing tables available (usually 255, but 1-255 user-defined, 0-255 total)
  - [ ] `iptables` or `nftables` support (we'll use iptables for now, design for both)
  - [ ] cgroup v1 or v2? (We'll use cgroup v1 net_cls for simplicity, but v2 also possible)
  - [ ] Polkit rules needed for iptables/route manipulation

- [ ] **Create proof-of-concept**:
  - [ ] Simple Python script that:
    - Creates two TUN devices: `tun0` and `tun1`
    - Brings them up with different IPs
    - Creates routing tables: `ip route add default via <gw1> dev tun0 table 1001`
    - Sets up iptables rule: `iptables -t mangle -A OUTPUT -m cgroup --cgroup 0x00110011 -j MARK --set-mark 0x3e9`
    - Adds rule: `ip rule add fwmark 0x3e9 table 1001`
    - Tests with two `curl` commands (one marked, one not) should use different routes
  - [ ] Measure performance overhead (should be minimal)
  - [ ] Test DNS (may leak if not careful - need per-tunnel DNS or DNS over TLS)

**Deliverable**: `SPECIFICATION.md` in docs/, PoC script in `examples/`

---

## 🏗️ Phase 1: Core Library (`libvpnmanager`) (Week 3-6)

### 1.1 Project Setup
- [ ] Create Python package structure:
  ```
  libvpnmanager/
  ├── pyproject.toml  (or setup.cfg + setup.py)
  ├── MANIFEST.in
  ├── README.md
  ├── src/
  │   └── libvpnmanager/
  │       ├── __init__.py
  │       ├── tunnel.py           # Tunnel dataclass
  │       ├── config.py           # ConnectionConfig types
  │       ├── status.py           # TunnelStatus enum
  │       ├── exceptions.py       # Custom exceptions
  │       ├── adapter.py          # VPNAdapter ABC
  │       ├── manager.py          # TunnelManager (orchestrator)
  │       ├── routing/
  │       │   ├── __init__.py
  │       │   ├── policy.py       # PolicyRouting (fwmark + routing tables)
  │       │   ├── namespace.py    # NamespaceRouting (future)
  │       │   └── base.py         # RoutingStrategy ABC
  │       ├── dbus/
  │       │   ├── __init__.py
  │       │   ├── service.py      # D-Bus service implementation
  │       │   ├── client.py       # D-Bus client proxy
  │       │   └── interfaces.py
  │       └── adapters/
  │           ├── __init__.py
  │           ├── base.py         # Base adapter
  │           ├── proton.py       # ProtonVPNAdapter
  │           └── dummy.py        # Dummy adapter for testing
  └── tests/
      ├── unit/
      └── integration/
  ```

- [ ] Set up build system:
  - [ ] `pyproject.toml` with `setuptools`
  - [ ] Dependencies: `dbus-fast`, `pydantic` (or attrs), `asyncstdlib`, `pyroute2` (optional, for routing)
  - [ ] Add `mypy`, `black`, `ruff`

- [ ] Write `README.md`

### 1.2 Data Models
- [ ] Define `Tunnel` dataclass:
  ```python
  @dataclass
  class Tunnel:
      name: str
      adapter: str
      device: str
      routing_strategy: str  # "policy" or "namespace"
      routing_metadata: Dict[str, Any]  # For policy: {"table": 1001, "fwmark": 0x3e9, "cgroup": "0x0011"}
      endpoint: Optional[str] = None
      connected_at: Optional[datetime] = None
      bytes_in: int = 0
      bytes_out: int = 0
      metadata: Dict[str, Any] = field(default_factory=dict)
  ```

- [ ] Define `ConnectionConfig` hierarchy (same as Option 1)
- [ ] Define `TunnelStatus` enum (same as Option 1)

### 1.3 Adapter Interface
- [ ] Define `VPNAdapter` ABC (same as Option 1, no changes needed)

### 1.4 Routing Engine - Policy Routing (`routing/policy.py`)
- [ ] Define `PolicyRouting` class:
  ```python
  class PolicyRouting:
      def __init__(self):
          self.tunnels: Dict[str, Tunnel] = {}
          self.table_counter = 1000  # Start at table 1000, increment
          self.fwmark_counter = 0x3e8  # Start at 0x3e8, increment (hex)
          self.cgroup_base = 0x00110011  # For cgroup net_cls (major:minor)

      async def create_tunnel_context(self, tunnel: Tunnel, device_name: str):
          """Set up routing table and fwmark for tunnel"""
          table_id = self.table_counter
          fwmark = self.fwmark_counter
          cgroup_val = self.cgroup_base + len(self.tunnels)

          # 1. Create routing table entry (in /etc/iproute2/rt_tables.d/ or via `ip` command)
          #    We'll just use `ip route` commands, no need to persist
          #    Table number is enough; `ip route` creates it on first use

          # 2. Add default route for this tunnel's device
          #    ip route add default via <vpn_gateway> dev {device_name} table {table_id}
          #    But we don't know gateway yet. Adapter will call `configure_routing` later

          # 3. Create cgroup for this tunnel
          cgroup_path = f"/sys/fs/cgroup/net_cls/vpn_{tunnel.name}"
          # mkdir -p {cgroup_path}
          # Write cgroup.classid: echo "{cgroup_val:#010x}" > {cgroup_path}/net_cls.classid

          # 4. Add iptables rule to mark packets from this cgroup
          #    iptables -t mangle -A OUTPUT -m cgroup --cgroup {cgroup_val:#010x} -j MARK --set-mark {fwmark}
          #    Mark all packets from processes in this cgroup

          # 5. Add ip rule to route marked packets via our table
          #    ip rule add fwmark {fwmark} lookup {table_id}

          tunnel.routing_metadata = {
              "table": table_id,
              "fwmark": fwmark,
              "cgroup_path": cgroup_path,
              "cgroup_value": cgroup_val,
          }
          self.tunnels[tunnel.name] = tunnel

      async def configure_tunnel_routing(self, tunnel: Tunnel, gateway: str):
          """After connection, set up the actual route"""
          meta = tunnel.routing_metadata
          table = meta["table"]
          device = tunnel.device

          # ip route add default via {gateway} dev {device} table {table}
          # Also add local network for device if needed

      async def assign_process(self, tunnel: Tunnel, pid: int):
          """Move process to tunnel's cgroup"""
          meta = tunnel.routing_metadata
          cgroup_path = meta["cgroup_path"]
          # echo {pid} > {cgroup_path}/cgroup.procs
          # This moves the process to the cgroup, causing iptables to mark its packets

      async def destroy_tunnel_context(self, tunnel: Tunnel):
          """Clean up routing resources"""
          meta = tunnel.routing_metadata
          if not meta:
              return

          # 1. Remove iptables rule
          # iptables -t mangle -D OUTPUT -m cgroup --cgroup {cgroup_val} -j MARK --set-mark {fwmark}

          # 2. Remove ip rule
          # ip rule del fwmark {fwmark} table {table}

          # 3. Remove routing table entries (flush)
          # ip route flush table {table}

          # 4. Remove cgroup
          # rmdir {cgroup_path}

          del self.tunnels[tunnel.name]
  ```

- [ ] Add error handling:
  - [ ] `RoutingTableExistsError`
  - [ ] `FwmarkInUseError`
  - [ ] `CgroupPermissionError`

- [ ] Consider using `pyroute2` library instead of subprocess:
  ```python
  import pyroute2
  ip = pyroute2.IPRoute()
  ip.route('add', dst='default', gateway=gateway, table=table_id, oif=ifindex)
  ip.rule('add', fwmark=fwmark, table=table_id)
  ```

  **Pros**: No subprocess, Python API, better error handling
  **Cons**: Extra dependency, may require root

### 1.5 Tunnel Manager
- [ ] `manager.py` (mostly same as Option 1, but routing differences)
  - [ ] Track tunnels with `routing_metadata`
  - [ ] Call `routing.create_tunnel_context()` when tunnel created
  - [ ] Call `routing.configure_tunnel_routing()` after adapter connects
  - [ ] Call `routing.assign_process()` when using switch/exec
  - [ ] Call `routing.destroy_tunnel_context()` on tunnel deletion

### 1.6 D-Bus Service & Client
- [ ] Same as Option 1 (no changes needed)
- [ ] Ensure `Tunnel` serialization includes `routing_metadata`

### 1.7 Proton VPN Adapter
- [ ] Mostly same as Option 1, but with routing differences:
  ```python
  async def connect(self, config: ProtonConnectionConfig, ...):
      # ... establish connection via proton-vpn-api-core
      # Get TUN device name (proton0, proton1, etc.)

      tunnel = Tunnel(
          name=config.tunnel_name,
          adapter="proton",
          device=device_name,
          routing_strategy="policy",
          routing_metadata={},  # Will be filled by manager
          ...
      )

      # Tell manager to create routing context
      await self.manager.routing.create_tunnel_context(tunnel)

      # Get gateway from connection (VPN server assigns IP with gateway)
      gateway = await self._extract_gateway_from_connector(connector)

      # Configure routing for this tunnel
      await self.manager.routing.configure_tunnel_routing(tunnel, gateway)

      return tunnel
  ```

  - [ ] Method to extract gateway IP from Proton connection (usually the server's tunnel IP minus 1 or from config)
  - [ ] Note: Proton may assign /32 IP with no gateway; then we need to route via directly connected network
    - In that case: `ip route add <server_ip> dev {device}` without gateway

**Key difference from Option 1**: Adapter doesn't move device to namespace; device stays in main namespace. The daemon just sets up routing tables and marks.

### 1.8 CLI - `protonvpn tunnel` commands
- [ ] `tunnel create` - Same as Option 1
- [ ] `tunnel delete` - Same
- [ ] `tunnel list` - Same, but show Table/Fwmark instead of Namespace
- [ ] `tunnel info` - Show routing metadata
- [ ] `tunnel switch` - **Different**:
  ```python
  async def switch(ctx, name):
      client = await get_manager_client()
      tunnel = await client.get_tunnel(name)
      meta = tunnel.routing_metadata

      # Create cgroup if not exists (should already exist from tunnel creation)
      cgroup_path = meta["cgroup_path"]

      # Move current shell's process to that cgroup
      # Write $$ (shell PID) to cgroup.procs
      with open(f"{cgroup_path}/cgroup.procs", "w") as f:
          f.write(str(os.getpid()))

      click.echo(f"Switched current shell to tunnel '{name}'")
      click.echo("All subsequent commands from this shell will use that tunnel")
      click.echo("To unmark: protonvpn tunnel switch default")
  ```

  **But**: Moving current process to cgroup affects all children. However, we can't move already-running shell? Actually we can: writing to `cgroup.procs` moves the process. But the shell itself might cache DNS, etc. Better approach: **don't move current shell**; instead, launch a new shell that inherits the cgroup:

  ```python
  # Instead, use:
  os.execlp("sh", "-c", f"""
      echo $$ > {cgroup_path}/cgroup.procs
      exec $SHELL
  """)
  # This replaces current process with new shell in cgroup
  ```

- [ ] `tunnel exec` - Similar to Option 1 but uses cgroup:
  ```python
  async def exec(ctx, name, command):
      tunnel = await client.get_tunnel(name)
      meta = tunnel.routing_metadata
      cgroup_path = meta["cgroup_path"]

      # We need to run command in the cgroup.
      # Can't easily do it from Python without creating subprocess in cgroup.
      # Solution: Use systemd-run or similar, OR just have user use `switch` first.

      # Simpler: Just print instructions
      click.echo("To run a command in this tunnel, either:")
      click.echo(f"1. Use 'protonvpn tunnel switch {name}' then run command")
      click.echo(f"2. Or: echo $$ > {cgroup_path}/cgroup.procs && {' '.join(command)}")

      # Or use systemd-run with property:
      # systemd-run --scope -p "Delegate=yes" -p "TasksMax=inf" --unit=vpn-app bash -c 'echo $$ > /sys/fs/cgroup/.../cgroup.procs && exec "$@"' -- command...
      # Too complex for CLI
  ```

  **Better UX**: Instead of `exec`, provide `protonvpn tunnel mark` that sets cgroup for current shell and all children. Then user runs commands normally. That's the `switch` approach.

  Revised CLI:
  ```bash
  protonvpn tunnel create work --country US     # Creates tunnel with table 1001, fwmark 0x3e9
  protonvpn tunnel mark work                   # Moves current shell to work's cgroup
  firefox                                      # Uses work tunnel (all children inherit)
  protonvpn tunnel mark default                # Move back to default routing
  ```

  Or:
  ```bash
  protonvpn tunnel run work -- curl ifconfig.me  # One-shot: create temp cgroup, run, cleanup
  ```

  We'll implement: `tunnel mark <name>` and `tunnel unmark`

**Deliverable**: CLI with policy-based routing control; simpler than namespaces

---

## 🛠️ Phase 2-5: Similar to Option 1

The remaining phases are **very similar** to Option 1 with only routing implementation differing:

- **Phase 2: Daemon** - Same D-Bus interface, but uses `PolicyRouting` class instead of `NetworkNamespaceRouting`
- **Phase 3: CLI** - Commands similar but `switch`/`exec` use cgroup manipulation instead of `nsenter`
- **Phase 4: Testing** - Integration tests check routing tables and iptables rules instead of namespaces
- **Phase 5: Packaging** - Same packaging structure

Key differences:
1. Daemon needs `CAP_NET_ADMIN` for `ip rule`/`ip route` and `iptables` (same as namespaces)
2. No `ip netns` commands needed
3. Tests verify `ip rule show` and `iptables -t mangle -L` instead of `ip netns list`
4. CLI `switch` command writes to `cgroup.procs` file instead of calling `nsenter`
5. More lightweight (no separate namespaces)

---

## 📊 Comparison: Option 1 vs Option 2 (Implementation Tasks)

| Task | Option 1 (Namespaces) | Option 2 (Policy Routing) |
|------|----------------------|--------------------------|
| Create TUN device | Same | Same |
| Move device to namespace | `ip link set dev netns <ns>` | Not needed (stay in main ns) |
| Configure IP | Same (but in ns) | Same (in main ns) |
| Set up routing | `ip netns exec ns ip route ...` | `ip route add ... table <N>` |
| Mark packets | Not needed (already in ns) | `iptables -t mangle -A OUTPUT -m cgroup ...` |
| Route selection | Namespace has its own table | `ip rule fwmark <X> table <N>` |
| Move process to context | `setns()` or `nsenter` | Write PID to `cgroup.procs` |
| Resource overhead | Higher (each ns has loopback, etc.) | Lower (shared stack) |
| Debugging | Need `nsenter` to inspect | Direct `ip addr`, `ip route` |
| Implementation complexity | Higher (namespace lifecycle) | Medium (cgroup + tables + iptables) |
| User command `switch` | `nsenter -n -m -t $$ $SHELL` | `echo $$ > /sys/.../cgroup.procs && $SHELL` |
| Compatibility | Needs kernel 3.9+ for netns | Needs IP_MULTIPLE_TABLES + cgroup (older kernels ok) |
| DNS | Per-ns systemd-resolved needed | Shared DNS (may leak) - need iptables REDIRECT to per-tunnel DNS forwarder? |
| Number of tunnels | ~100-200 (memory) | ~200 (routing tables) |

---

## 🎯 Decision Guide: Which Option to Choose?

### Choose Option 1 (Network Namespaces) if:
- ✓ You want **complete isolation** (separate DNS, firewall, network interfaces)
- ✓ Need to run apps that bind to specific interface (should still work in Option 2 but more complex)
- ✓ Security is paramount (namespace isolation is stronger)
- ✓ Willing to handle `systemd-resolved` per-ns complexity
- ✓ Expect fewer than 50 concurrent tunnels
- ✓ Targeting modern kernels (3.9+)

### Choose Option 2 (Policy Routing) if:
- ✓ Want **simpler implementation** and easier debugging
- ✓ Don't need per-ns DNS (can use DoH/DoT to avoid leak)
- ✓ Want lower overhead (can handle 100+ tunnels)
- ✓ Want compatibility with older kernels (3.0+ maybe)
- ✓ Prefer to see all TUN devices directly in `ip addr`
- ✓ Accept that some advanced features (per-ns firewall) may be limited

---

## My Recommendation

**Start with Option 2 (Policy Routing)** for the following reasons:

1. **Faster to implement** - No namespace lifecycle management, simpler CLI
2. **Easier to debug** - All devices visible, can use standard tools
3. **Sufficient for most use cases** - Per-app routing works fine
4. **Can add Option 1 later** as an advanced feature for users who need full isolation

However, **DNS is a challenge**:
- Policy routing doesn't isolate DNS resolver
- Apps may use their own DoH which bypasses routing
- Solution: Set up local DNS forwarder per tunnel (dnsmasq) and redirect UDP/53 via iptables to that forwarder
- That adds complexity

**Namespace approach**:
- Each namespace can have its own `/etc/resolv.conf`
- Systemd-resolved can run per-ns if configured
- Cleaner DNS isolation

If DNS isolation is critical, consider **Option 1**. If you can live with shared DNS or implement per-tunnel DNS forwarder, **Option 2** is simpler.

---

## Hybrid Approach (Future)

Could support **both** routing strategies:
- `--routing=namespace` or `--routing=policy` flag
- Daemon configured to use one strategy globally
- Or per-tunnel: some tunnels use namespace, others use policy
- CLI same interface regardless

This allows users to choose based on their needs.

---

## Next Steps

1. **Choose Option** (1 or 2) based on your requirements
2. **Implement PoC** for chosen option (verify it works)
3. **Follow Phase 1** to build core library
4. **Adapt existing adapter** to work with new routing
5. **Update CLI** with tunnel commands

Both TODO lists are structured identically after Phase 1, so you can switch later if needed.

---

**This is the complete TODO for Option 2 (Policy Routing).** The directory `multi-tunnel-policy-routing/` contains this file and will be used for implementation.

**Project Name**: libvpnmanager + proton-vpn-manager (same as Option 1, just different routing strategy)
