# Multi-Tunnel VPN with Network Namespaces - Technical Specification

**Option 1: Network Namespace Isolation**
**Project**: `libvpnmanager` + `proton-vpn-manager`
**Date**: 2026-03-16
**Status**: Phase 0 - Draft Specification

---

## 1. Overview

This specification defines an application-independent library and daemon for managing multiple concurrent VPN tunnels, each isolated in its own network namespace. The architecture supports multiple VPN backends (Proton VPN, Psiphon, WireGuard, etc.) through a plugin-style adapter system.

### Key Goals

- **Multiple concurrent tunnels**: Run US + Japan + Germany VPNs simultaneously
- **Complete isolation**: Each tunnel has separate routing, DNS, firewall
- **Per-application routing**: Run specific apps through specific tunnels via `nsenter`
- **Vendor neutrality**: Adapter pattern allows Proton, Psiphon, WireGuard, etc.
- **D-Bus control interface**: CLI and GUI tools communicate via D-Bus
- **Security**: Daemon runs as root with fine-grained Polkit rules, CLI as user

---

## 2. System Requirements

### Kernel & Userspace

- **Linux kernel**: 3.9+ (network namespaces are stable in all modern kernels)
- **iproute2**: `ip` command for namespace management (version 4.0+)
- **TUN/TAP support**: Kernel module `tun` must be loaded (usually automatic)
- **systemd-resolved** (optional but recommended): Per-namespace DNS via stub listener

### Capabilities Required

The daemon (`proton-vpn-manager`) must run with:

- `CAP_NET_ADMIN`: Create/modify network interfaces, routing tables
- `CAP_SYS_ADMIN`: Create network namespaces (implicit with netns)
- These can be granted via Polkit rules or by running as root

### Resource Limits

- **Maximum TUN devices**: Typically 256+ per system (check `/proc/sys/net/dev_max` if needed)
- **Memory per namespace**: ~1-2 MB for network stack structures
- **Practical limit**: 50-100 tunnels depending on RAM
- **Routing table IDs**: Use 1000-2000 range for policy routing fallback

### Filesystem

- `/var/run/netns/`: Traditional location for netns mount points (managed by `ip netns`)
- `/dev/net/tun`: TUN/TAP device node (created by kernel, major 10 minor 200)
- `/sys/class/net/`: Sysfs entries for network devices
- `/etc/resolv.conf` in each namespace: Can be bind-mounted from host or configured separately

---

## 3. Core Data Models

### 3.1 Tunnel Status Enum

```python
from enum import Enum

class TunnelStatus(Enum):
    DISCONNECTED = "disconnected"   # Tunnel exists but not connected
    CONNECTING = "connecting"       # Connection in progress
    CONNECTED = "connected"         # Active and routing traffic
    DISCONNECTING = "disconnecting" # Disconnection in progress
    ERROR = "error"                 # Failed state with error condition
```

### 3.2 Tunnel Dataclass

```python
from dataclasses import dataclass, field
from datetime import datetime
from typing import Dict, Any, Optional

@dataclass
class Tunnel:
    """
    Represents a VPN tunnel instance.
    """
    name: str                          # User-provided tunnel name (unique)
    adapter: str                       # Adapter type: "proton", "psiphon", etc.
    device: str                        # TUN device name: "proton0", "tun1", etc.
    namespace: Optional[str] = None    # Network namespace name (e.g., "vpn_work")
    endpoint: Optional[str] = None     # VPN server/exit node identifier
    connected_at: Optional[datetime] = None
    bytes_in: int = 0                  # Traffic counters (bytes received)
    bytes_out: int = 0                 # Traffic counters (bytes sent)
    metadata: Dict[str, Any] = field(default_factory=dict)
        # Adapter-specific data: server config, protocol, etc.
```

### 3.3 Connection Config Hierarchy

```python
from dataclasses import dataclass
from typing import Optional

@dataclass
class ConnectionConfig:
    """
    Base configuration for creating a tunnel.
    """
    adapter: str                       # Required: adapter to use
    tunnel_name: str                   # Required: unique tunnel identifier

@dataclass
class ProtonConnectionConfig(ConnectionConfig):
    """
    Proton VPN specific configuration.
    """
    server_id: Optional[str] = None    # Proton server logical ID
    country: Optional[str] = None      # Country code (e.g., "US", "JP")
    city: Optional[str] = None         # City name (optional)
    protocol: str = "wireguard"        # "wireguard", "openvpn-udp", "openvpn-tcp"
    features: Dict[str, bool] = field(default_factory=dict)
        # Feature flags: safe_mode, nat_type, etc.

@dataclass
class PsiphonConnectionConfig(ConnectionConfig):
    """
    Psiphon configuration.
    """
    entry_country: Optional[str] = None  # Entry server country
    exit_country: Optional[str] = None   # Desired exit country
    transport_protocol: str = "tcp"      # "tcp" or "udp"
   畔??
```

*(Continuing in the next message due to length)*

---

## 4. VPN Adapter Interface

All VPN backends implement this abstract base class:

```python
from abc import ABC, abstractmethod
from typing import List, Tuple

class VPNAdapter(ABC):
    """
    Abstract base class for VPN adapters.
    Each VPN type (Proton, Psiphon, WireGuard) implements this interface.
    """

    @abstractmethod
    async def connect(self, config: ConnectionConfig, progress_callback=None) -> Tunnel:
        """
        Establish a VPN connection.

        Args:
            config: Connection configuration (type-specific subclass)
            progress_callback: Optional callable for progress updates

        Returns:
            Tunnel object with populated fields (device, namespace, etc.)

        Raises:
            AuthenticationError: If credentials invalid
            ConnectionError: If network/server unreachable
            ConfigurationError: If config invalid
        """
        pass

    @abstractmethod
    async def disconnect(self, tunnel: Tunnel) -> None:
        """
        Disconnect an active tunnel.

        Args:
            tunnel: Tunnel object to disconnect

        Raises:
            TunnelNotFoundError: If tunnel not active
        """
        pass

    @abstractmethod
    async def get_status(self, tunnel: Tunnel) -> TunnelStatus:
        """
        Get current status of a tunnel.

        Args:
            tunnel: Tunnel object

        Returns:
            TunnelStatus enum value
        """
        pass

    @abstractmethod
    def list_tunnels(self) -> List[Tunnel]:
        """
        List all tunnels currently managed by this adapter.

        Returns:
            List of Tunnel objects (connected or disconnected but created)
        """
        pass

    @abstractmethod
    def get_capabilities(self) -> AdapterCapabilities:
        """
        Return supported features for this adapter.

        Returns:
            AdapterCapabilities dataclass
        """
        pass

    @abstractmethod
    async def get_traffic_stats(self, tunnel: Tunnel) -> Tuple[int, int]:
        """
        Get traffic statistics for a tunnel.

        Args:
            tunnel: Tunnel object

        Returns:
            (bytes_in, bytes_out) tuple
        """
        pass

    @abstractmethod
    async def cleanup(self) -> None:
        """
        Cleanup all resources on daemon shutdown.
        Disconnect all active tunnels, release resources.
        """
        pass
```

### 4.1 Adapter Capabilities

```python
from dataclasses import dataclass

@dataclass
class AdapterCapabilities:
    """
    Describes what features an adapter supports.
    """
    multi_tunnel: bool = False          # Can create multiple concurrent connections
    supports_protocols: List[str] = field(default_factory=list)
    max_tunnels: Optional[int] = None   # None = unlimited, else integer limit
    supports_per_app_routing: bool = False  # Native per-app routing
    supports_kill_switch: bool = False      # Network lock/kill switch
    supports_dns_isolation: bool = False    # Per-tunnel DNS
```

---

## 5. Routing Engine: Network Namespace Strategy

The routing engine implements namespace lifecycle management.

### 5.1 NetworkNamespaceRouting Class

```python
import asyncio
from typing import Dict, Set

class NetworkNamespaceRouting:
    """
    Implements network namespace isolation strategy.
    Each tunnel gets its own Linux network namespace.
    """

    def __init__(self):
        self.namespaces: Dict[str, str] = {}
            # tunnel_name -> namespace_name (e.g., "work" -> "vpn_work")
        self.tunnels_in_ns: Dict[str, Set[str]] = {}
            # namespace_name -> set of tunnel device names
        self._lock = asyncio.Lock()

    async def create_namespace(self, tunnel_name: str) -> str:
        """
        Create a new network namespace for a tunnel.

        Args:
            tunnel_name: Unique tunnel identifier

        Returns:
            Namespace name (e.g., "vpn_work")

        Raises:
            NamespaceExistsError: If namespace already exists
            NamespacePermissionError: If ip netns fails
        """
        async with self._lock:
            ns_name = f"vpn_{tunnel_name}"

            # Check if already exists
            result = await self._run_command(["ip", "netns", "list"])
            if ns_name in result.stdout:
                raise NamespaceExistsError(f"Namespace {ns_name} already exists")

            # Create namespace
            await self._run_command(["ip", "netns", "add", ns_name])
            self.namespaces[tunnel_name] = ns_name
            self.tunnels_in_ns[ns_name] = set()

            return ns_name

    async def move_device_to_namespace(self, device: str, namespace: str) -> None:
        """
        Move a TUN device into a network namespace.

        Args:
            device: TUN device name (e.g., "tun0", "proton0")
            namespace: Target network namespace

        Raises:
            DeviceNotFoundError: If device doesn't exist in host netns
            NamespaceNotFoundError: If namespace doesn't exist
        """
        # Verify device exists in current namespace
        result = await self._run_command(["ip", "link", "show", device])
        if result.returncode != 0:
            raise DeviceNotFoundError(f"Device {device} not found")

        # Verify namespace exists
        if namespace not in await self._list_namespaces():
            raise NamespaceNotFoundError(f"Namespace {namespace} not found")

        # Move device: ip link set <device> netns <namespace>
        await self._run_command(["ip", "link", "set", device, "netns", namespace])

        # Track
        if namespace in self.tunnels_in_ns:
            self.tunnels_in_ns[namespace].add(device)

    async def configure_namespace_network(self, tunnel: Tunnel, vpn_gateway: str, vpn_ip: str) -> None:
        """
        Inside the namespace: configure IP address, default route, DNS.

        Args:
            tunnel: Tunnel object (must have .namespace and .device set)
            vpn_gateway: Gateway IP from VPN server (e.g., "10.7.0.1")
            vpn_ip: Assigned client IP (e.g., "10.7.0.2")

        Note: This runs commands inside the namespace via `ip netns exec`.
        """
        ns = tunnel.namespace
        device = tunnel.device

        if not ns or not device:
            raise ValueError("Tunnel must have namespace and device set")

        # Bring up device inside namespace
        await self._run_command_in_ns(ns, ["ip", "link", "set", device, "up"])

        # Configure IP address
        await self._run_command_in_ns(ns, ["ip", "addr", "add", f"{vpn_ip}/32", "dev", device])

        # Set default route via VPN gateway
 await self._run_command_in_ns(ns, ["ip", "route", "add", "default", "via", vpn_gateway, "dev", device])

        # Configure DNS (Option A: bind mount host's resolv.conf)
        # Option B: write custom resolv.conf for this namespace
        # Option C: use systemd-resolved with per-link DNS (Advanced)
        await self._configure_namespace_dns(ns, vpn_gateway)

    async def _configure_namespace_dns(self, namespace: str, dns_server: str) -> None:
        """
        Configure DNS resolution inside the namespace.
        Strategy: bind-mount a custom resolv.conf into the namespace.

        Alternative: if systemd-resolved is running, configure per-link DNS
        via /run/systemd/resolve/netif/<interface>/.
        """
        # Implementation detail: create resolv.conf with nameserver
        resolv_content = f"nameserver {dns_server}\n"
        resolv_path = f"/etc/resolv.conf.d/{namespace}"

        # Write temporary resolv.conf
        import tempfile
        with tempfile.NamedTemporaryFile(mode='w', delete=False) as f:
            f.write(resolv_content)
            temp_path = f.name

        # Inside namespace, replace /etc/resolv.conf
        # Note: Requires /etc to be writable. If not, use bind mount:
        # mount --bind /path/to/temp/resolv.conf /etc/resolv.conf
        await self._run_command_in_ns(namespace, ["cp", temp_path, "/etc/resolv.conf"])

    async def destroy_namespace(self, tunnel_name: str) -> None:
        """
        Delete a namespace and clean up references.

        Args:
            tunnel_name: Tunnel to destroy

        Note: Deleting namespace automatically removes devices inside.
        """
        async with self._lock:
            ns_name = self.namespaces.get(tunnel_name)
            if not ns_name:
                return  # Already cleaned up

            try:
                await self._run_command(["ip", "netns", "delete", ns_name])
            except Exception as e:
                # Log warning but continue cleanup
                print(f"Warning: failed to delete namespace {ns_name}: {e}")

            # Clean up references
            self.namespaces.pop(tunnel_name, None)
            self.tunnels_in_ns.pop(ns_name, None)

    async def list_namespaces(self) -> List[str]:
        """
        List all VPN namespaces currently on system.

        Returns:
            List of namespace names
        """
        result = await self._run_command(["ip", "netns", "list"])
        # Output format: "vpn_work (id: 2)\n"
        namespaces = []
        for line in result.stdout.strip().split('\n'):
            if line:
                ns_name = line.split()[0]
                if ns_name.startswith('vpn_'):
                    namespaces.append(ns_name)
        return namespaces

    async def _run_command(self, cmd: List[str]) -> subprocess.CompletedResult:
        """Helper: run command and return result."""
        # Implementation uses asyncio.create_subprocess_exec
        pass

    async def _run_command_in_ns(self, namespace: str, cmd: List[str]):
        """Helper: run command inside namespace via ip netns exec."""
        full_cmd = ["ip", "netns", "exec", namespace] + cmd
        await self._run_command(full_cmd)

    async def cleanup_all(self):
        """Delete all managed namespaces (on daemon shutdown)."""
        async with self._lock:
            for tunnel_name in list(self.namespaces.keys()):
                try:
                    await self.destroy_namespace(tunnel_name)
                except Exception as e:
                    print(f"Error cleaning up namespace for {tunnel_name}: {e}")
```

---

## 6. D-Bus Interface Specification

The daemon exposes an D-Bus interface for CLI control.

### 6.1 Service Identity

- **Bus Type**: Session or System bus (depends on deployment)
- **Service Name**: `org.protonvpn.Manager`
- **Object Path**: `/org/protonvpn/Manager`
- **Interface**: `org.protonvpn.Manager`
- **Optional**: Legacy compatibility with `org.freedesktop.NetworkManager.VPN`

### 6.2 Methods

| Method | Input | Output | Description |
|--------|-------|--------|-------------|
| `CreateTunnel` | `a{sv} config` | `a{sv} tunnel_info` | Create and optionally connect a tunnel |
| `DestroyTunnel` | `s name` | `b` | Completely remove tunnel |
| `ConnectTunnel` | `s name` | `b` | Connect an existing tunnel |
| `DisconnectTunnel` | `s name` | `b` | Disconnect a tunnel (keep config) |
| `ListTunnels` | - | `aa{sv}` | List all tunnels with info |
| `GetTunnelStatus` | `s name` | `a{sv}` | Get detailed status for one tunnel |
| `GetTrafficStats` | `s name` | `(tt)` (uint64, uint64) | Bytes in/out |
| `RegisterAdapter` | `s adapter_type` | `b` | Register an adapter by type name |

All methods return error `org.protonvpn.Error.TunnelNotFound` if tunnel doesn't exist.

### 6.3 Signals

| Signal | Payload | Description |
|--------|---------|-------------|
| `TunnelStateChanged` | `(ss)` `(name, state)` | Tunnel status changed |
| `TunnelCreated` | `(s)` `(name)` | New tunnel created (but not connected) |
| `TunnelDestroyed` | `(s)` `(name)` | Tunnel removed |
| `AdapterRegistered` | `(ss)` `(type, version)` | New adapter loaded |

### 6.4 Example D-Bus XML Introspection

```xml
<!DOCTYPE node PUBLIC "-//freedesktop//DTD D-BUS Object Introspection 1.0//EN"
 "http://www.freedesktop.org/standards/dbus/1.0/introspect.dtd">
<node>
  <interface name="org.protonvpn.Manager">
    <method name="CreateTunnel">
      <arg type="a{sv}" name="config" direction="in"/>
      <arg type="a{sv}" name="tunnel_info" direction="out"/>
    </method>

    <method name="DestroyTunnel">
      <arg type="s" name="name" direction="in"/>
      <arg type="b" name="success" direction="out"/>
    </method>

    <signal name="TunnelStateChanged">
      <arg type="s" name="name"/>
      <arg type="s" name="state"/>
    </signal>
  </interface>
</node>
```

---

## 7. User-Space Tools

### 7.1 CLI Commands

The `protonvpn` CLI (this repository) adds new commands:

```bash
# Tunnel management
protonvpn tunnel create <name> --country US --protocol wireguard
protonvpn tunnel list
protonvpn tunnel connect <name>
protonvpn tunnel disconnect <name>
protonvpn tunnel destroy <name>
protonvpn tunnel info <name>

# Per-application routing (namespace approach)
protonvpn tunnel switch <name>   # Start new shell in tunnel's namespace
protonvpn tunnel exec <name> -- <command>  # Run command in tunnel ns

# Legacy (backward compatibility)
protonvpn connect              # Behaves as before (single tunnel)
```

### 7.2 Namespace Switching Implementation

`protonvpn tunnel switch` uses `nsenter`:

```python
# Implementation in cli/commands.py
async def tunnel_switch(self, name: str):
    # 1. Query daemon for tunnel namespace via D-Bus
    tunnel = await self.client.get_tunnel(name)
    if not tunnel.namespace:
        raise ValueError(f"Tunnel {name} has no namespace")

    # 2. Launch interactive shell via nsenter
    # Equivalent to: nsenter -t <self-pid> -n -m -u -i -p $SHELL -i
    os.execvp("nsenter", [
        "nsenter", "-t", str(os.getpid()),
        "-n", "-m", "-u", "-i", "-p",
        tunnel.namespace,
        os.environ.get("SHELL", "/bin/bash"), "-i"
     ])
```

**Note**: `nsenter` needs to be installed (part of util-linux).

---

## 8. Polkit Rules

The daemon requires privileges to:

- Create network namespaces (`CAP_SYS_ADMIN`)
- Create/modify TUN devices (`CAP_NET_ADMIN`)
- Modify routing tables and firewall rules

Polkit rule (`/etc/polkit-1/rules.d/60-protonvpn.rules`):

```javascript
polkit.addRule(function(action, subject) {
    // Allow users in wheel/sudo group to manage VPN tunnels
    if (action.id == "org.protonvpn.manager.create-tunnel" ||
        action.id == "org.protonvpn.manager.destroy-tunnel" ||
        action.id == "org.protonvpn.manager.connect" ||
        action.id == "org.protonvpn.manager.disconnect") {

        // Check if user is in appropriate group
        if (subject.user == "root") {
            return polkit.Result.YES;
        }

        // For non-root, check group membership
        const groups = subject.groups;
        if (groups.indexOf("wheel") >= 0 || groups.indexOf("sudo") >= 0) {
            return polkit.Result.YES;
        }

        // Or could require authentication:
        // return polkit.Result.AUTH_SELF;
    }
});
```

The daemon registers actions with Polkit during startup via `polkit. Authority`.

---

## 9. Systemd Service

Daemon runs as a system service (Type=simple or dbus).

`/usr/lib/systemd/system/proton-vpn-manager.service`:

```ini
[Unit]
Description=Proton VPN Tunnel Manager
Documentation=man:proton-vpn-manager(8)
After=network-online.target
Wants=network-online.target

[Service]
Type=dbus
BusName=org.protonvpn.Manager
ExecStart=/usr/bin/proton-vpn-manager
Restart=on-failure
RestartSec=5
CapabilityBoundingSet=CAP_NET_ADMIN CAP_SYS_ADMIN
 AmbientCapabilities=CAP_NET_ADMIN CAP_SYS_ADMIN
NoNewPrivileges=false
PrivateTmp=true
ProtectSystem=strict
ProtectHome=true
SystemCallFilter=@system-service

# Security: Drop privileges but keep capabilities
# Could run as non-root: protonvpn user
User=protonvpn
Group=protonvpn

[Install]
WantedBy=multi-user.target
```

---

## 10. Limitations & Future Work

### Current Limitations (Option 1)

1. **Memory overhead**: ~2-10 MB per namespace
2. **Complexity**: Namespace lifecycle management, cleanup
3. **Debugging**: Requires `nsenter` to inspect namespace state
4. **DNS**: Need per-namespace resolv.conf; systemd-resolved integration non-trivial
5. **IPv6**: Must be configured separately per namespace
6. **Max tunnels**: Limited to ~50-100 by memory and TUN device limits

### Open Questions

- **Daemon multi-tunnel support**: Proton's `proton-vpn-api-core` currently supports only one connection. We must either:
  a) Fork and extend it to support multiple connectors
  b) Run multiple daemon instances (complex)
  c) Design adapter to work with single-tunnel limitation (not true multi-tunnel)

- **TUN device naming**: Should the daemon create generically named devices (`tun0`, `tun1`) or namespaced ones (`proton0`, `psiphon0`)? Recommendation: adapter chooses, manager tracks.

- **Persistent tunnels**: Should tunnels survive daemon restart? Likely no for security, but configs can be saved.

---

## 11. Success Criteria

By end of Phase 0, we will have:

1. ✅ **SPECIFICATION.md** (this document) reviewed and finalized
2. ✅ **Proof-of-concept script** that demonstrates basic namespace tunnel working
3. ✅ **PoC validation**: Can run `curl` inside namespace and confirm traffic exits via TUN
4. ✅ **Performance baseline**: Measure overhead vs single-tunnel
5. ✅ **API contracts** defined and approved by stakeholders
6. ✅ **Decision**: Proceed with Option 1 or pivot to Option 2

---

## Appendix A: Example PoC Flow

The PoC script will perform:

```bash
#!/usr/bin/env python3
# Phase 0 PoC: Validate namespace-based tunneling

import subprocess
import os

def run(cmd):
    subprocess.run(cmd, check=True)

# 1. Create namespace
run(["ip", "netns", "add", "test_vpn"])

# 2. Create TUN device (requires root)
run(["ip", "tuntap", "add", "tun_test", "mode", "tun"])
run(["ip", "link", "set", "tun_test", "up"])

# 3. Move TUN to namespace
run(["ip", "link", "set", "tun_test", "netns", "test_vpn"])

# 4. Inside namespace: configure IP and route
run(["ip", "netns", "exec", "test_vpn", "ip", "addr", "add", "10.8.0.2/32", "dev", "tun_test"])
run(["ip", "netns", "exec", "test_vpn", "ip", "link", "set", "tun_test", "up"])

# 5. (Mock) Set up host side of tunnel (would be real VPN in daemon)
run(["ip", "addr", "add", "10.8.0.1/32", "dev", "tun_test"])
run(["ip", "link", "set", "tun_test", "up"])

# 6. Configure namespace default route via TUN
run(["ip", "netns", "exec", "test_vpn", "ip", "route", "add", "default", "via", "10.8.0.1"])

# 7. Enable IP forwarding and NAT on host (for internet access)
run(["sysctl", "-w", "net.ipv4.ip_forward=1"])
run(["iptables", "-t", "nat", "-A", "POSTROUTING", "-o", "eth0", "-j", "MASQUERADE"])

# 8. Test: Run curl inside namespace (should use tunnel)
result = subprocess.run(["ip", "netns", "exec", "test_vpn", "curl", "-s", "ifconfig.me"], capture_output=True, text=True)
print("Public IP from namespace:", result.stdout.strip())

# 9. Cleanup
run(["ip", "netns", "delete", "test_vpn"])
run(["ip", "link", "delete", "tun_test"])
```

---

**End of SPECIFICATION.md**

