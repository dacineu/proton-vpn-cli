# Proton Daemon (proton-vpn-api-core) Analysis for Multi-Tunnel Support

**Date**: 2026-03-16
**Status**: Preliminary analysis based on existing knowledge; requires codebase access
**Target**: proton-vpn-api-core repository

---

## 1. What We Know About Current Architecture

### 1.1 Observed from proton-vpn-cli Imports

From `proton/vpn/cli/core/controller.py` and other files:

```python
from proton.vpn.core.api import ProtonVPNAPI
from proton.vpn.core.connection import VPNStateSubscriber, VPNConnection, VPNConnector
from proton.vpn.core.session_holder import ClientTypeMetadata
from proton.vpn.core.settings import Settings
from proton.vpn.session import ServerList
from proton.vpn.session.dataclasses.servers import LogicalServer, ServerFeatureEnum
from proton.vpn.connection.enum import ConnectionStateEnum
from proton.vpn.connection import states
```

### 1.2 Key Classes Inferred

- **ProtonVPNAPI**: Main entry point, initialized with `ClientTypeMetadata`
  - Method: `get_vpn_connector() -> VPNConnector`
  - Likely also: `get_server_list()`, `login()`, `logout()`, etc.

- **VPNConnector**: Factory for creating VPN connections
  - Method: `connect(server: LogicalServer, protocol: str) -> VPNConnection`
  - Method: `disconnect()`
  - Method: `get_connection_state() -> ConnectionStateEnum`
  - **Single-tunnel limitation**: Appears to maintain only one active connection

- **VPNConnection**: Represents an active VPN connection
  - Method: `get_tun_device_name() -> str` (we need this!)
  - Method: `get_connection_state() -> ConnectionStateEnum`
  - Method: `get_server() -> LogicalServer`
  - Method: `close()`
  - Possibly: `get_traffic_stats() -> (rx, tx)`

- **VPNStateSubscriber**: Callback interface for async state updates
  - Method: `state_updated(state: ConnectionStateEnum, connection: VPNConnection)`

- **ProtonVPNAPI login flow**:
  - Clerk: seems to be where APICredentials come from
  - API: high-level interface that uses VPNConnector internally
  - Session management, server lists, etc.

### 1.3 Daemon Structure (proton-vpn-local-agent)

There's also `proton-vpn-local-agent` which runs as root and manages TUN devices.
The VPNConnector probably communicates with this via D-Bus or similar.

TUN device creation seems to happen in the local agent, not in the API itself.

---

## 2. Critical Questions That Need Answers

To design the multi-tunnel extension, we need to answer:

1. **Does `ProtonVPNAPI.get_vpn_connector()` return a new instance each call?**
   - If yes, we could create multiple connectors and they'd coexist?
   - If no (singleton), we need to create MultiTunnelVPNConnector as replacement

2. **What does `VPNConnector.connect()` actually do?**
   - Does it create TUN device directly?
   - Does it call local agent via D-Bus?
   - Can we pass a custom TUN device name parameter?

3. **How is the TUN device name determined?**
   - Hardcoded "proton0" somewhere?
   - Configurable via environment or config?
   - Assigned by local agent?

4. **Can multiple VPNConnection objects exist simultaneously?**
   - Does the local agent support multiple concurrent connections?
   - What happens if we call `connect()` twice on same/different connectors?

5. **How does the local agent track connections?**
   - By D-Bus serial?
   - By connector instance?
   - Would need to identify TUN by tunnel_name or some ID

6. **What's the API for querying active connections?**
   - Is there a `list_connections()` method?
   - How does reconnect/refresh work?

---

## 3. Proposed Solution: MultiTunnelVPNConnector

### 3.1 Design Goals

1. **Backward compatible**: Existing single-tunnel API still works unchanged
2. **Multi-tunnel**: Create N concurrent tunnels, each with unique TUN
3. **Minimal changes**: Extend existing classes, don't rewrite
4. **Clear migration**: Old code works; new code uses MultiTunnelVPNConnector

### 3.2 Proposed API

```python
class MultiTunnelVPNConnector(VPNConnector):
    """
    Enhanced VPNConnector that supports multiple concurrent tunnels.

    Usage:
        connector = MultiTunnelVPNConnector()
        conn1 = await connector.connect("work", server1, "wireguard")  # Creates tun0
        conn2 = await connector.connect("personal", server2, "wireguard")  # Creates tun1

        # Both active simultaneously
        assert conn1.get_tun_device_name() == "proton0"
        assert conn2.get_tun_device_name() == "proton1"

        # Can disconnect individually
        await connector.disconnect("work")  # Only disconnects work
        # personal remains connected

        # Query by tunnel name
        conn = connector.get_connection("personal")
        if conn:
            status = conn.get_connection_state()

        # List all tunnels
        for name, conn in connector.list_connections():
            print(f"{name}: {conn.get_tun_device_name()}")
    """

    def __init__(self, api: ProtonVPNAPI):
        super().__init__()
        self._api = api
        self._connections: Dict[str, VPNConnection] = {}
        self._next_id = 0  # For TUN device naming

    async def connect(
        self,
        tunnel_name: str,
        server: LogicalServer,
        protocol: str,
        custom_tun_name: Optional[str] = None
    ) -> VPNConnection:
        """
        Create a new tunnel connection.

        Args:
            tunnel_name: Unique identifier for this tunnel
            server: Target server
            protocol: VPN protocol (wireguard, openvpn-udp, etc.)
            custom_tun_name: Optional specific TUN device name (for advanced usage)

        Returns:
            VPNConnection object

        Raises:
            TunnelExistsError: If tunnel_name already connected
            ConnectionError: If connection fails
        """
        if tunnel_name in self._connections:
            raise TunnelExistsError(f"Tunnel '{tunnel_name}' already exists")

        # Determine TUN device name
        if custom_tun_name:
            tun_name = custom_tun_name
        else:
            tun_name = f"proton{self._next_id}"
            self._next_id += 1

        # Create connection - this needs support in the underlying local-agent
        # Need to pass tun_name to local agent somehow
        connection = await self._create_connection(
            tunnel_name=tunnel_name,
            server=server,
            protocol=protocol,
            tun_device_name=tun_name
        )

        self._connections[tunnel_name] = connection
        return connection

    async def disconnect(self, tunnel_name: str):
        """Disconnect a specific tunnel."""
        conn = self._connections.pop(tunnel_name, None)
        if conn:
            await conn.close()
        # else: warn?

    def get_connection(self, tunnel_name: str) -> Optional[VPNConnection]:
        """Get connection by tunnel name."""
        return self._connections.get(tunnel_name)

    def list_connections(self) -> Dict[str, VPNConnection]:
        """Return dict of tunnel_name -> connection."""
        return dict(self._connections)

    # Override parent single-tunnel methods for backward compatibility
    async def connect_single(self, server: LogicalServer, protocol: str) -> VPNConnection:
        """
        Legacy single-tunnel API for backward compatibility.
        Creates/connects to tunnel named "default".
        """
        # If "default" exists, disconnect and reconnect?
        if "default" in self._connections:
            await self.disconnect("default")
        return await self.connect("default", server, protocol)

    async def disconnect_all(self):
        """Disconnect all tunnels."""
        for name in list(self._connections.keys()):
            await self.disconnect(name)

    # Private helper - this needs to be implemented by talking to local agent
    async def _create_connection(
        self,
        tunnel_name: str,
        server: LogicalServer,
        protocol: str,
        tun_device_name: str
    ) -> VPNConnection:
        """
        Create a new VPNConnection with specific TUN device.

        This is the key method that must be implemented.
        It needs to:
          1. Establish connection to Proton server
          2. Ask local-agent to create TUN with name tun_device_name
          3. Return VPNConnection object representing that connection

        Current single-tunnel code probably does:
          connector = await api.get_vpn_connector()
          await connector.connect(server, protocol)  # Uses fixed "proton0"

        We need to inject custom TUN name.
        """
        # Placeholder - actual implementation depends on local-agent API
        raise NotImplementedError("Requires modified proton-vpn-local-agent")
```

---

## 4. Required Changes in proton-vpn-api-core

### 4.1 File: `proton/vpn/core/api.py` (or wherever ProtonVPNAPI lives)

**Current code** (likely):

```python
class ProtonVPNAPI:
    def __init__(self, metadata: ClientTypeMetadata):
        self._metadata = metadata
        self._connector = None

    async def get_vpn_connector(self) -> VPNConnector:
        if self._connector is None:
            self._connector = VPNConnector(self)
        return self._connector
```

**Change to**:

```python
class ProtonVPNAPI:
    def __init__(self, metadata: ClientTypeMetadata):
        self._metadata = metadata
        self._connector = None

    async def get_vpn_connector(self, multi_tunnel: bool = False) -> VPNConnector:
        """
        Get a VPN connector.

        Args:
            multi_tunnel: If True, return MultiTunnelVPNConnector.
                         If False (default), return single-tunnel (backward compat).

        Returns:
            VPNConnector (single or multi)
        """
        if multi_tunnel:
            if not hasattr(self, '_multi_connector') or self._multi_connector is None:
                self._multi_connector = MultiTunnelVPNConnector(self)
            return self._multi_connector
        else:
            if self._connector is None:
                self._connector = VPNConnector(self)
            return self._connector
```

### 4.2 File: `proton/vpn/core/connection.py`

**Current**: `class VPNConnector`

We need to add:

```python
class MultiTunnelVPNConnector(VPNConnector):
    """
    Multi-tunnel extension of VPNConnector.
    """

    def __init__(self, api):
        super().__init__(api)
        self._tunnels: Dict[str, VPNConnection] = {}
        self._next_device_id = 0

    async def connect(
        self,
        tunnel_name: str,
        server: LogicalServer,
        protocol: Optional[str] = None,
        **kwargs  # For backward compatibility
    ) -> VPNConnection:
        """
        Connect a named tunnel.

        Note: This overrides parent's connect() signature.
        To maintain backward compatibility, we add separate method:
        connect_single(server, protocol) for old code.
        But since parent uses connect(server, protocol), we need to
        detect args and support both patterns.

        Better: Add new method connect_tunnel(tunnel_name, ...) and keep
        connect() as single-tunnel for backward compatibility.
        """
        # Implementation as shown in section 3.2
        pass

    async def disconnect(self, tunnel_name: str = None):
        """
        Disconnect a tunnel.

        If tunnel_name is None, disconnect the "default" or raise error.
        """
        if tunnel_name is None:
            # Legacy behavior - disconnect default
            await self.disconnect("default")
        else:
            # Multi-tunnel disconnect
            conn = self._tunnels.pop(tunnel_name, None)
            if conn:
                await conn.close()

    def get_connection(self, tunnel_name: str) -> Optional[VPNConnection]:
        return self._tunnels.get(tunnel_name)

    def list_tunnel_names(self) -> List[str]:
        return list(self._tunnels.keys())
```

### 4.3 File: Where local agent communication happens

The VPNConnector likely talks to `proton-vpn-local-agent` via D-Bus.
We need to modify the D-Bus call to include desired TUN device name.

**Search for**:
- `VPNConnector.connect()` implementation
- Calls to local agent: probably `await self._api.get_local_agent().connect_vpn(...)`
- Or via D-Bus: `bus.call(...)` with interface `org.protonvpn.LocalAgent`

**We need to inject**: `tun_device_name` parameter

**Example modification**:

```python
# Current (pseudocode):
async def connect(self, server, protocol):
    local_agent = self._api.get_local_agent()
    await local_agent.start_connection(server, protocol)
    # Local agent internally decides to use "proton0"

# Modified:
async def _start_connection(self, server, protocol, tun_device_name=None):
    local_agent = self._api.get_local_agent()

    # Need to add parameter to local agent API
    if tun_device_name:
        await local_agent.start_connection(server, protocol, tun_device_name)
    else:
        # Fall back to default "proton0" or auto-assign
        await local_agent.start_connection(server, protocol)
```

### 4.4 File: `proton/vpn/local/agent/...` (proton-vpn-local-agent)

This daemon runs as root and actually creates TUN devices.

**We need to modify it to accept custom TUN names**.

Search for:
- `class LocalAgent` or similar
- Method that creates TUN: likely uses `open("/dev/net/tun")` + `ioctl(TUNSETIFF)`
- Look for hardcoded "proton0"

**Current behavior** (likely):

```python
async def start_vpn_connection(self, server_config):
    # Create TUN device
    tun_name = "proton0"  # Hardcoded!
    self._tun = self._create_tun(tun_name)
    # Configure routing, etc.
```

**Change to**:

```python
async def start_vpn_connection(self, server_config, tun_device_name=None):
    if tun_device_name is None:
        # Auto-assign: find first available protonX
        tun_device_name = self._find_available_tun_name()

    # Validate name isn't already used
    if tun_device_name in self._active_tuns:
        raise DeviceExistsError(f"TUN device {tun_device_name} already in use")

    self._tun = self._create_tun(tun_device_name)
    # Keep track: self._active_tuns[tun_device_name] = connection_info
```

**Need to track**: Multiple TUNs simultaneously, each independent routing.

This is the **biggest change** - the local agent must support concurrent TUN devices with independent routing. Might need separate routing tables per TUN? Or use network namespaces as we planned?

---

## 5. Alternative: Purely User-Space Multi-Tunnel (No Local Agent Changes)

Is it possible to avoid modifying local agent? Let's think:

1. **Run multiple local agent instances?**
   - Each needs unique D-Bus name (conflict)
   - Each needs root (CAP_NET_ADMIN)
   - Complex, not clean

2. **Move TUN from one namespace to another after creation?**
   - If local agent creates proton0 in default namespace
   - We could move it to a different namespace via ip link set netns
   - But we need multiple TUNs, not just moving same TUN
   - Doesn't solve multi-tunnel

3. **Use different D-Bus sessions?**
   - Each user session could have own local agent
   - But they all need same root privileges
   - Not practical

**Verdict**: **Local agent modification is required** for true multi-tunnel.

---

## 6. Step-by-Step Implementation Plan for Daemon

### Phase 1: Prepare Local Agent for Multiple TUNs

1. **Add TUN device registry** in LocalAgent:
   ```python
   class LocalAgent:
       def __init__(self):
           self._tuns: Dict[str, TunDevice] = {}  # name -> TunDevice
   ```

2. **Modify connection creation** to accept `tun_name` parameter:
   ```python
   async def create_connection(self, server_config, tun_name=None):
       if tun_name is None:
           tun_name = self._allocate_tun_name()
       if tun_name in self._tuns:
           raise ...
       tun = self._create_tun_device(tun_name)
       self._tuns[tun_name] = tun
       # Configure routing for this TUN independently
       return connection
   ```

3. **Ensure independent routing per TUN**:
   - Each TUN gets its own routing table? (for policy routing)
   - Or we move TUN to namespace (what we want)
   - Local agent needs to support namespaces? Or we do that from our daemon?

**Actually**: Our architecture (Option 1) has the daemon move TUN to namespace. So local agent just needs to:
- Create TUN with given name (any name we request)
- Not configure global default route (let daemon handle)
- Provide API to query TUN name

So local agent changes:
- Accept `tun_device_name` parameter
- Create TUN with that name instead of hardcoded "proton0"
- Possibly skip routing configuration (daemon will do it after moving to ns)

### Phase 2: Modify VPNConnector to Support Named Tunnels

1. Create `MultiTunnelVPNConnector` class
2. Implement `connect(tunnel_name, server, protocol)` that:
   - Generates/accepts TUN name
   - Calls local agent with that TUN name
   - Tracks connection object by tunnel_name
3. Implement `disconnect(tunnel_name)`, `get_connection(tunnel_name)`, `list_tunnels()`
4. Keep existing `connect(server, protocol)` as legacy (uses "default" tunnel)

### Phase 3: ProtonVPNAPI Integration

1. Add `get_vpn_connector(multi_tunnel=False)` parameter
2. Return MultiTunnelVPNConnector when multi_tunnel=True
3. Maybe default to multi_tunnel in future major version

---

## 7. Specific File Modifications (Proposed)

Based on typical structure, here are files likely needing changes:

### In proton-vpn-api-core/

```
 proton/
   vpn/
     core/
       api.py                    # Add multi_tunnel parameter to get_vpn_connector()
       connection/
         __init__.py             # Export MultiTunnelVPNConnector
         vpn_connector.py        # Create MultiTunnelVPNConnector subclass
         vpn_connection.py       # Maybe store tunnel_name in VPNConnection
       local/
         agent.py                # Accept tun_device_name, support multiple TUNs
         agent_dbus.py           # If D-Bus interface, add tun_name parameter
```

**Estimated changes**:
- `api.py`: +20 lines (new parameter, factory logic)
- `vpn_connector.py`: +200 lines (new MultiTunnelVPNConnector class)
- `local/agent.py`: +100 lines (accept tun_name, track multiple TUNs)
- `local/agent_dbus.py`: +50 lines (update D-Bus method signature)

Total: ~400 lines of new/changed code in daemon.

---

## 8. Backward Compatibility Strategy

**Goal**: Existing single-tunnel code continues to work unchanged.

**Strategy**:
1. Keep `VPNConnector.connect(server, protocol)` unchanged - still creates/uses "default" tunnel
2. Add **new methods** for multi-tunnel:
   - `MultiTunnelVPNConnector.connect(tunnel_name, server, protocol)`
   - `MultiTunnelVPNConnector.disconnect(tunnel_name)`
   - `MultiTunnelVPNConnector.get_connection(tunnel_name)`
   - `MultiTunnelVPNConnector.list_tunnel_names()`
3. Do NOT modify existing `VPNConnection` class (just add `get_tun_device_name()` if missing)
4. In `ProtonVPNAPI.get_vpn_connector()`:
   - default: returns single-tunnel connector (backward compat)
   - with `multi_tunnel=True`: returns multi-tunnel connector

**Migration path**:
- v0.x: Single-tunnel only (current)
- v1.x: Introduce `get_vpn_connector(multi_tunnel=True)` and MultiTunnelVPNConnector
- v2.x: Make multi_tunnel the default, deprecate single-tunnel

---

## 9. Testing Strategy for Modified Daemon

### Unit Tests (in proton-vpn-api-core)
- Test `MultiTunnelVPNConnector.connect()` creates unique TUN names
- Test can have 2+ connections active simultaneously
- Test `get_connection()` returns correct connection
- Test `disconnect()` only affects one tunnel
- Test `list_tunnel_names()` shows all active

### Integration Tests
- Create tunnel "A" → get TUN name "proton0" (or assigned)
- Create tunnel "B" → get TUN name "proton1"
- Both connected simultaneously
- Traffic stats separate for each TUN
- Disconnect "A" → "B" still works
- Reconnect "A" → gets possibly different TUN?

### System Tests
- Use real Proton servers
- Verify each tunnel gets different exit IP
- Test maximum concurrent tunnels (Proton limit ~10 devices per account)
- Test reconnect logic per tunnel

---

## 10. Open Questions Requiring Codebase Inspection

1. **Where is TUN device name determined?**
   - In local agent? In connector? Configurable?
   - Find hardcoded "proton0"

2. **How does local agent expose D-Bus API?**
   - Interface name: `org.protonvpn.LocalAgent`?
   - Methods: `Connect`, `Disconnect`, etc.
   - Need to add parameter

3. **What's the lifecycles?**
   - When does VPNConnector get created/destroyed?
   - Can it survive across multiple connect/disconnect?
   - Does VPNConnection stay valid after disconnect?

4. **How are credentials/session managed?**
   - ProtonVPNAPI handles login, session refresh
   - Does each connector share session? Probably yes via API object

5. **How to get traffic stats per connection?**
   - Is there `VPNConnection.get_stats()`?
   - Or read from `/sys/class/net/tunX/statistics`?

6. **What about IPv6?**
   - Does daemon configure IPv6?
   - Namespace strategy needs IPv6 too

---

## 11. Immediate Next Action: Codebase Exploration

**We need to actually look at the proton-vpn-api-core code**.

Action items:
1. Clone the repository (need access credentials)
2. Locate the key files listed above
3. Read `VPNConnector.connect()` implementation
4. Find where TUN device is created
5. Document actual class names, methods, signatures
6. Write precise diffs for each file

**Deliverable**: `PROTON_API_DETAILED_ANALYSIS.md` with:
- Actual class diagrams
- Method signatures (current)
- Exact lines that need modification
- Proposed patches (git diff format)

---

## 12. Can We Proceed Without Modification?

**Option**: Keep ProtonVPNAdapter pure user-space, use policy routing (Option 2) instead of namespaces.

But wait - even policy routing needs multiple TUNs to have multiple exit servers. Single TUN = single tunnel. So multi-tunnel **requires** multiple TUN devices.

**Unless**: We use proxies (SOCKS5 per tunnel) inside same TUN? But that's not true VPN per tunnel.

**Conclusion**: **Multi-tunnel requires daemon changes**. No way around it.

---

## 13. Suggested Approach

1. **Don't fork yet** - First write a detailed design document and submit to Proton team as issue/feature request
2. **Offer to implement** - Show we've done 80% of the work (libvpnmanager); just need daemon changes
3. **Collaborate** - Maybe they have internal multi-tunnel work already? Align with their roadmap
4. **If they say no** - Consider alternative: use wireguard-go directly (bypass proton-vpn-api-core), but lose Proton features (NetShield, Secure Core, etc.)

---

## Summary

**What we know**: Current proton-vpn-api-core appears single-tunnel only.

**What we need**: Multi-tunnel support at daemon level:
- Modified LocalAgent to accept custom TUN names
- MultiTunnelVPNConnector class
- Ability to have N concurrent connections

**Estimated daemon changes**: ~400 lines across 4-5 files.

**Next step**: Get the actual code and produce line-by-line modification plan.

---

**TODO**: Access proton-vpn-api-core repository and complete this analysis with actual code references.
