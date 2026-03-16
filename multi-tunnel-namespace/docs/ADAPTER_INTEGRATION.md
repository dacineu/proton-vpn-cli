# ProtonVPNAdapter Integration Design

**Date**: 2026-03-16
**Component**: ProtonVPNAdapter for libvpnmanager
**Dependency**: `proton-vpn-api-core` (the daemon)

---

## 1. Current Proton VPN Architecture

### 1.1 Existing Components

The current Proton VPN CLI uses:

```
proton-vpn-cli (this repo)
   |
   v
proton.vpn.core.api.ProtonVPNAPI   [from proton-vpn-api-core]
   |
   +-- get_vpn_connector() -> VPNConnector
           |
           v
      VPNConnector.connect(server, protocol)
           |
           v
      VPNConnection (represents active connection)
           |
           +-- TUN device created by proton-vpn-local-agent (daemon)
           +-- Events: ConnectionStateEnum.CONNECTED, DISCONNECTED, etc.
           +-- get_tun_device_name() -> "proton0" (or similar)
```

### 1.2 Key Classes (from proton-vpn-api-core)

Located in `proton.vpn.core`:

- `ProtonVPNAPI` - Main entry point, requires `ClientTypeMetadata`
- `VPNConnector` - Factory for creating connections
  - `connect(server: LogicalServer, protocol: str) -> VPNConnection`
  - `disconnect()`
  - `get_connection_state() -> ConnectionStateEnum`
- `VPNConnection` - Represents an active connection
  - `get_tun_device_name() -> str` - **We need this!**
  - `get_connection_state() -> ConnectionStateEnum`
  - `get_server() -> LogicalServer`
  - `close()`
- `VPNStateSubscriber` - Callback interface for state changes
  - `state_updated(state: ConnectionStateEnum, connection: VPNConnection)`

### 1.3 Current Limitations

**Proton daemon is SINGLETON-BASED**:

- `ProtonVPNAPI` appears to be a singleton (one instance per session)
- `get_vpn_connector()` likely returns the same connector each time
- Only **one** TUN device active at a time (`proton0`)
- Old connection is terminated when new `connect()` is called

**Multi-tunnel requires changes**:

1. Must be able to create **multiple VPNConnector instances** (or one connector that can manage multiple connections)
2. Each connection must have **unique TUN device name** (currently hardcoded to "proton0")
3. Need API to **query all active TUN devices** from daemon
4. Daemon must not kill previous connection when new one created

---

## 2. Required Daemon Changes

### 2.1 Option A: Extend proton-vpn-api-core (Preferred)

Fork and modify `proton-vpn-api-core` to:

```python
class MultiTunnelVPNConnector:
    def __init__(self):
        self._connections: Dict[str, VPNConnection] = {}
        self._next_id = 0

    def connect(self, tunnel_name: str, server: LogicalServer, protocol: str) -> VPNConnection:
        """Create a new *additional* connection with unique TUN name."""
        if tunnel_name in self._connections:
            raise TunnelExistsError(tunnel_name)

        # Generate unique TUN name: proton0, proton1, proton2...
        tun_name = f"proton{self._next_id}"
        self._next_id += 1

        # Create connection (modified local-agent must accept tun_name parameter)
        connection = self._create_connection(tunnel_name, server, protocol, tun_name)
        self._connections[tunnel_name] = connection
        return connection

    def disconnect(self, tunnel_name: str):
        if tunnel_name in self._connections:
            self._connections[tunnel_name].close()
            del self._connections[tunnel_name]

    def get_connection(self, tunnel_name: str) -> Optional[VPNConnection]:
        return self._connections.get(tunnel_name)

    def list_tunnels(self) -> List[str]:
        return list(self._connections.keys())

    # Existing single-tunnel API for backward compatibility
    def connect_legacy(self, server, protocol):  # Uses default "default" tunnel
        return self.connect("default", server, protocol)
```

Changes needed in **proton-vpn-local-agent**:
- Accept `tun_device_name` parameter when establishing connection
- Support creating multiple TUN devices (they are independent)
- Track multiple active sessions, keyed by tunnel_name

### 2.2 Option B: Workaround Without Daemon Changes (Not True Multi-tunnel)

If daemon cannot be modified, we could:
- Run **multiple daemon instances** on different ports (complex, conflicts)
- Use **different Linux users** each with own D-Bus session (heavy)
- Accept **single-tunnel limitation** and only use namespaces for isolation within one tunnel (defeats purpose)

**Conclusion**: Daemon modification is **required** for true multi-tunnel.

---

## 3. ProtonVPNAdapter Implementation Plan

### 3.1 Architecture

```python
class ProtonVPNAdapter(VPNAdapter):
    def __init__(self, manager: TunnelManager):
        self.manager = manager
        self.api: Optional[ProtonVPNAPI] = None
        self.connector: Optional[MultiTunnelVPNConnector] = None
        self._local_tunnels: Dict[str, Tunnel] = {}
            # Maps tunnel_name -> Tunnel object we created

    async def connect(config: ProtonConnectionConfig) -> Tunnel:
        await self._ensure_api()
        await self._ensure_connector()

        # 1. Find server based on config.country/server_id
        server = await self._find_server(config)

        # 2. Connect via multi-tunnel connector
        connection = await self.connector.connect(
            tunnel_name=config.tunnel_name,
            server=server,
            protocol=config.protocol
        )

        # 3. Wait for CONNECTED state
        await self._wait_for_state(connection, ConnectionStateEnum.CONNECTED)

        # 4. Get TUN device name
        tun_device = connection.get_tun_device_name()  # e.g., "proton1"

        # 5. Create Tunnel object
        tunnel = Tunnel(
            name=config.tunnel_name,
            adapter="proton",
            device=tun_device,
            endpoint=server.server_name,
            connected_at=datetime.utcnow(),
            metadata={
                "protocol": config.protocol,
                "server_id": server.id,
                "vpn_connection": connection,  # Keep reference
            }
        )
        self._local_tunnels[config.tunnel_name] = tunnel

        # 6. Let manager create namespace and move TUN (via routing strategy)
        # Manager calls routing.create_tunnel_context()
        # Then calls routing.move_device_to_namespace(tunnel.device, tunnel.namespace)
        # Then configures inside namespace via routing.configure_namespace_network(...)

        return tunnel

    async def disconnect(tunnel: Tunnel):
        # Tell connector to disconnect
        await self.connector.disconnect(tunnel.name)
        self._local_tunnels.pop(tunnel.name, None)
```

### 3.2 Integration Points with Routing

After `adapter.connect()` returns the Tunnel with `device` set, the `TunnelManager` does:

```python
# In TunnelManager.connect_tunnel():
connected_tunnel = await adapter.connect(config)

# Update tunnel with device info
tunnel.device = connected_tunnel.device

# Create routing context (namespace for Option 1)
routing_metadata = await self.routing.create_tunnel_context(tunnel_name)
tunnel.namespace = routing_metadata.get("namespace")

# Adapter-specific: now configure network inside namespace
# This is done via routing strategy, but needs gateway IP and DNS
# The adapter must provide these from the VPN connection

# So we need: adapter.get_network_config(tunnel) -> (gateway_ip, dns_servers)
# And then: routing.configure_namespace_network(namespace, device, vpn_ip, gateway, dns)
```

**New method needed in VPNAdapter ABC**: `get_network_config(tunnel)` returns gateway and DNS servers.

### 3.3 Handling Connection State Changes

- The adapter should subscribe to `VPNStateSubscriber` events
- On DISCONNECTED (unexpected), emit `TunnelStateChanged` signal via D-Bus
- Manager may need to update its tunnel status

---

## 4. Implementation Steps

### Step 1: Study proton-vpn-api-core

**Action**: Clone and explore the proton-vpn-api-core repository.
- Find `ProtonVPNAPI` class
- Find `VPNConnector` interface
- Find how `get_tun_device_name()` works
- Identify what changes needed for multi-tunnel

**Deliverable**: `PROTON_API_ANALYSIS.md` with findings.

### Step 2: Create ProtonVPNAdapter

Create `src/adapters/proton.py`:

```python
from proton.vpn.core.api import ProtonVPNAPI
from proton.vpn.core.connection import VPNConnector, VPNConnection, ConnectionStateEnum
from proton.vpn.core.session_holder import ClientTypeMetadata

from .base import VPNAdapter
from ..models.tunnel import Tunnel
from ..models.config import ProtonConnectionConfig
from ..models.exceptions import ConnectionError, AuthenticationError

class ProtonVPNAdapter(VPNAdapter):
    # Implement all abstract methods
```

Need to handle:
- API initialization (login via existing session or reauth)
- Server lookup from Proton server list
- Multi-tunnel connector (or use modified API)
- State change subscription

### Step 3: Modify TODO_OPTION1.md to reflect current progress

Mark Phase 1 tasks as complete, update Phase 2-3 with actual implementation status.

### Step 4: Implement CLI `tunnel` commands

In the existing proton CLI codebase (`proton/vpn/cli/commands/`), add:

```python
@tunnel.command()
@click.argument("name")
@click.option("--country", required=True)
@click.option("--protocol", default="wireguard")
async def create(name, country, protocol):
    """Create and connect a named tunnel."""
    # Use Controller's new tunnel_client to talk to daemon
    # config = ProtonConnectionConfig(tunnel_name=name, country=country, protocol=protocol)
    # await client.create_tunnel(config, connect=True)
```

Commands needed:
- `protonvpn tunnel create <name> --country US [--protocol wireguard]`
- `protonvpn tunnel list`
- `protonvpn tunnel switch <name>` - uses `nsenter`
- `protonvpn tunnel exec <name> -- <command>` - uses `nsenter`
- `protonvpn tunnel disconnect <name>`
- `protonvpn tunnel destroy <name>`

### Step 5: Integrate libvpnmanager into existing CLI

- Add `multi-tunnel-namespace/src/libvpnmanager` as git submodule or package
- Update `pyproject.toml` to depend on libvpnmanager
- Modify `Controller` to use both old single-tunnel mode and new multi-tunnel mode
- Provide backward compatibility: `protonvpn connect` without `--tunnel-name` uses existing code path

---

## 5. Integration Challenges

### 5.1 TUN Device Name Collision

**Problem**: Proton daemon currently uses hardcoded "proton0". Need unique names.

**Solution**: Modify daemon to accept device name parameter when creating TUN.

### 5.2 Session/Login Sharing

**Problem**: Each tunnel would need its own session if using separate daemon instances.

**Solution**: Single daemon manages all tunnels, shares session/auth cookies.

### 5.3 Traffic Stats per Tunnel

**Problem**: Current daemon reports stats for the single connection.

**Solution**: Modified daemon must track stats per tunnel (different TUN devices have separate stats from `/sys/class/net/tunX/statistics`).

### 5.4 Kill Switch

**Problem**: Global kill switch affects all tunnels or none.

**Solution**: Per-tunnel kill switch is complex. Could implement as policy: if any tunnel active, kill switch blocks all non-VPN traffic. Or make kill switch per-tunnel via iptables rules per namespace (Option 1) or fwmark per table (Option 2).

### 5.5 Connection Limits

Proton accounts may have limit on concurrent connections (e.g., 10 devices). Multi-tunnel counts each tunnel as a "device". Need to track count and warn user.

---

## 6. Testing Strategy

### Unit Tests (Already Created)
- Models: serialization, config -> types
- Routing: mocked subprocess, namespace creation logic

### Integration Tests (Need to Create)
- Real namespace creation with sudo (run in CI with privileged container)
- Full tunnel lifecycle with DummyAdapter
- D-Bus service roundtrip

### System Tests (Manual)
- Create 2+ tunnels with real Proton (after daemon changes)
- Verify isolation: apps in different namespaces use different exit IPs
- Verify DNS: each namespace resolves correctly
- Performance: measure overhead per tunnel

---

## 7. Backward Compatibility

**Goal**: Existing `protonvpn connect` must keep working exactly as before.

**Strategy**:
- New commands are under `protonvpn tunnel ...`
- Old `protonvpn connect` → Manager uses single-tunnel mode, no namespace
- Transition: users can adopt gradually
- In future (v2.0), could deprecate single-tunnel mode

---

## 8. Open Questions

1. **Can proton-vpn-api-core be modified to support multi-tunnel?**
   - Need to check code structure. Might be significant refactor.

2. **Should we support both routing strategies?**
   - Library is designed for both, but daemon and CLI need to pick one
   - Could make it configurable, but increases testing burden

3. **Who will implement the daemon changes?**
   - This is the biggest coordination need
   - May require working with Proton engineering team

4. **Should the daemon run as root or with capabilities?**
   - Polkit can grant capabilities to non-root user
   - Running as root with security sandboxing is also acceptable

---

## 9. Next Actions

1. **Immediate**: Clone and analyze `proton-vpn-api-core` codebase
2. Write `PROTON_API_ANALYSIS.md`
3. Draft PR/issue for Proton team proposing multi-tunnel support
4. Begin implementing `ProtonVPNAdapter` with TODO about needed daemon API
5. Start CLI `tunnel` commands skeleton

---

**Bottom line**: The libvpnmanager library is ready. Now we need to connect it to the real Proton backend, which requires upstream daemon changes. The first step is analyzing the daemon code to understand what modifications are needed.
