# Upstream Daemon Work: proton-vpn-api-core

**⚠️ EXTERNAL DEPENDENCY**: This work needs to be done in the separate `proton-vpn-api-core` repository
**Status**: 🔴 **NOT STARTED** (Blocking all real Proton VPN integration)
**Impact**: Without this, ProtonVPNAdapter cannot function with real VPN connections
**Last Updated**: 2026-03-16

---

## 🚨 Critical Blocker

The multi-tunnel VPN project **cannot proceed with real Proton VPN connections** until changes are made to `proton-vpn-api-core`. The current daemon is single-tunnel only.

---

## 📊 Overview

**Repository**: `proton-vpn-api-core` (separate from this repository)
**Required work**: Implement `MultiTunnelVPNConnector` that supports multiple concurrent connections with unique TUN devices
**Estimated effort**: 4-8 weeks (depending on familiarity with codebase)
**Owner**: Proton VPN daemon team (needs their review/approval first)

---

## ✅ Current State (Single-Tunnel Limitation)

### Existing Architecture

```python
# Current: proton-vpn-api-core
from proton.vpn.core.api import ProtonVPNAPI

api = ProtonVPNAPI()
connector = api.get_vpn_connector()  # Singleton
connection = connector.connect(server, protocol)  # Creates "proton0"
# Any subsequent connect() kills previous connection
```

**Key limitations**:
1. `ProtonVPNAPI.get_vpn_connector()` returns a **singleton**
2. Only one `VPNConnection` active at a time
3. TUN device name is hardcoded to `"proton0"` by the local agent
4. Calling `connect()` on an active connection terminates it first

---

## 🎯 Required Changes

### Option A: MultiTunnelVPNConnector Class (Preferred)

Add a new class that manages multiple concurrent connections without breaking backward compatibility.

#### 1. Create `MultiTunnelVPNConnector`

**File**: `proton/vpn/core/api.py` or new `proton/vpn/core/multitunnel.py`

```python
class MultiTunnelVPNConnector:
    """
    Manages multiple concurrent VPN connections, each with its own TUN device.

    Unlike the singleton VPNConnector, this class allows creating multiple
    independent connections, each identified by a unique tunnel_name.
    """

    def __init__(self):
        self._connections: Dict[str, VPNConnection] = {}
        self._next_id: int = 0
        self._lock = asyncio.Lock()

    async def connect(
        self,
        tunnel_name: str,
        server: LogicalServer,
        protocol: str,
        **kwargs
    ) -> VPNConnection:
        """
        Create a new VPN connection with a unique TUN device.

        Args:
            tunnel_name: Unique identifier for this tunnel (e.g., "work", "personal")
            server: LogicalServer to connect to
            protocol: Protocol to use (wireguard, openvpn-udp, etc.)
            **kwargs: Additional connection parameters

        Returns:
            VPNConnection object representing the active connection

        Raises:
            TunnelExistsError: If tunnel_name already exists
            ConnectionError: If connection fails
        """
        async with self._lock:
            if tunnel_name in self._connections:
                raise TunnelExistsError(f"Tunnel '{tunnel_name}' already exists")

            # Generate unique TUN name
            tun_name = f"proton{self._next_id}"
            self._next_id += 1

            # Create connection
            # IMPORTANT: Modify local agent to accept `tun_device_name` parameter
            connection = await self._create_connection(
                tunnel_name=tunnel_name,
                server=server,
                protocol=protocol,
                tun_device_name=tun_name,
                **kwargs
            )

            self._connections[tunnel_name] = connection
            return connection

    async def disconnect(self, tunnel_name: str):
        """Disconnect a specific tunnel."""
        async with self._lock:
            if tunnel_name in self._connections:
                await self._connections[tunnel_name].close()
                del self._connections[tunnel_name]

    async def get_connection(self, tunnel_name: str) -> Optional[VPNConnection]:
        """Get active connection by name."""
        return self._connections.get(tunnel_name)

    def list_tunnels(self) -> List[str]:
        """Return list of active tunnel names."""
        return list(self._connections.keys())

    async def disconnect_all(self):
        """Disconnect all active tunnels."""
        async with self._lock:
            for conn in self._connections.values():
                try:
                    await conn.close()
                except Exception:
                    pass  # Best effort
            self._connections.clear()

    def get_tun_device_name(self, tunnel_name: str) -> Optional[str]:
        """Get the TUN device name for a tunnel."""
        conn = self._connections.get(tunnel_name)
        if conn:
            return conn.get_tun_device_name()
        return None
```

#### 2. Modify `VPNConnection` (or ensure it exposes TUN name)

**Requirement**: `VPNConnection` must have method `get_tun_device_name() -> str`

**Current**: Likely exists but check:
```python
class VPNConnection:
    def get_tun_device_name(self) -> str:
        """Return the TUN device name (e.g., 'proton0', 'proton1')."""
        # Implementation should return the device name
        pass
```

**If not present**: Add it to `VPNConnection` class.

#### 3. Modify Local Agent to Accept Custom TUN Name

**File**: `proton/vpn/core/local_agent/` (or similar)

The local agent (running as root) creates TUN devices via `openconnect` or `wg-quick` or direct TUN allocation.

**Needed change**:
- Accept `tun_device_name` parameter in connection request
- Instead of letting system auto-select TUN (which gives "proton0"), explicitly create the named TUN
- Or allocate, then rename to unique name

**Example** (pseudocode):
```python
# Current local agent receives:
{
    "action": "connect",
    "server": {...},
    "protocol": "wireguard"
}

# Required change:
{
    "action": "connect",
    "server": {...},
    "protocol": "wireguard",
    "tun_device_name": "proton1"  # NEW parameter
}

# Local agent then:
# - Creates TUN with name tun_device_name (or renames after creation)
# - Configures it
# - Returns: {"tun_device": "proton1", ...}
```

**Implementation depends on how local agent creates TUN**:
- **WireGuard**: `wg-quick` allows interface name via `wg0.conf` setting (Interface.Name=)
- **OpenVPN**: `--dev tun0` specifies device name
- **IKEv2**: `charon` settings
- **Direct TUN**: `open("/dev/net/tun", ...)` with `ifr.name` set

**Action**: Study the local agent code to see exactly how it allocates TUN devices and add parameter.

#### 4. Add to `ProtonVPNAPI`

**Option**: Add method to get multi-tunnel connector:

```python
class ProtonVPNAPI:
    def __init__(self, ...):
        self._multitunnel_connector = None  # Lazy init

    def get_multitunnel_connector(self) -> MultiTunnelVPNConnector:
        """Return a MultiTunnelVPNConnector for managing multiple tunnels."""
        if self._multitunnel_connector is None:
            self._multitunnel_connector = MultiTunnelVPNConnector()
        return self._multitunnel_connector
```

**Or** replace the singleton `get_vpn_connector()` entirely? But that would break existing single-tunnel users. Safer to add new method and keep old one as singleton.

---

## 📋 Detailed Implementation Plan

### Phase 1: Analysis (Week 1)

**Tasks**:
1. [ ] **Clone and explore proton-vpn-api-core repo**
2. [ ] Locate:
   - `ProtonVPNAPI` class (likely `proton/vpn/core/api.py`)
   - `get_vpn_connector()` method
   - `VPNConnector` class
   - `VPNConnection` class
   - `connect()` implementation
   - Local agent (probably `proton/vpn/core/local_agent/` or `proton/vpn/core/daemon/`)
3. [ ] Document:
   - How TUN device is created (exact code path)
   - Where device name is determined
   - How connections are tracked (if at all)
   - What prevents multiple connections (is it a singleton, or does API kill previous?)
4. [ ] Identify exact files and lines to modify
5. [ ] Write detailed plan (this document) with actual code snippets

**Deliverable**: `PROTON_API_ANALYSIS.md` with:
- Current architecture diagram
- Key classes and their roles
- TUN device creation code
- Specific modification plan

### Phase 2: Prototype (Week 2)

**Tasks**:
1. [ ] **Fork proton-vpn-api-core**
2. [ ] Create branch `feature/multi-tunnel`
3. [ ] **Add `MultiTunnelVPNConnector` class** (as above)
4. [ ] **Add `get_multitunnel_connector()` to `ProtonVPNAPI`**
5. [ ] **Modify local agent**:
   - Add `tun_device_name` parameter to connection request
   - Ensure TUN is created/configured with specified name
   - Return device name in response
6. [ ] **Add `get_tun_device_name()` to `VPNConnection`** if not present
7. [ ] **Write unit tests** in proton-vpn-api-core:
   - Test MultiTunnelVPNConnector.connect() with multiple tunnels
   - Test disconnect() and reconnect with different name
   - Test unique TUN names (proton0, proton1, proton2)
   - Test error on duplicate tunnel name
8. [ ] **Run existing tests** to ensure no regression

**Deliverable**: Working prototype fork with unit tests

### Phase 3: Review with Proton Team (Week 3)

**Tasks**:
1. [ ] **Submit PR or design doc** to Proton daemon team
2. [ ] Present:
   - Problem: single-tunnel daemon blocks multi-tunnel feature
   - Solution: MultiTunnelVPNConnector + tun_device_name param
   - Compatibility: Old singleton still works, new API additive
   - Testing: Unit tests included
3. [ ] Address feedback
4. [ ] Possibly co-develop with daemon team
5. [ ] Get approval for PR

**Deliverable**: PR submitted and approved (or design approved)

### Phase 4: Implementation (Weeks 4-7)

**Tasks**:
1. [ ] **Address PR feedback** (iterate)
2. [ ] **Expand unit tests** (edge cases, error handling)
3. [ ] **Add integration tests** in daemon repo:
   - Test actual TUN device creation with multiple tunnels
   - Test namespace operations (if daemon does that)
   - Test simultaneous connections
   - Test disconnection and cleanup
4. [ ] **Add documentation** in daemon codebase
5. [ ] **Update examples** in daemon repo (if any)
6. [ ] **Merge PR** (with team approval)

**Deliverable**: Multi-tunnel support merged to main branch

### Phase 5: Integrate into libvpnmanager (Week 8)

**Tasks**:
1. [ ] **Update ProtonVPNAdapter** to use MultiTunnelVPNConnector:
   ```python
   def __init__(self, api: ProtonVPNAPI):
       self.api = api
       self.connector = api.get_multitunnel_connector()
       self.connections: Dict[str, VPNConnection] = {}

   async def connect(self, tunnel_name, server, protocol):
       conn = await self.connector.connect(
           tunnel_name=tunnel_name,
           server=server,
           protocol=protocol
       )
       self.connections[tunnel_name] = conn
       # Extract network config from connection
       # (gateway, DNS servers)
   ```
2. [ ] Update `get_capabilities()` to advertise `multi_tunnel=True`
3. [ ] Update `list_tunnels()` to return from self.connections
4. [ ] Update `disconnect()` to call `connector.disconnect(tunnel_name)`
5. [ ] Update `get_network_config()` to get from connection
6. [ ] **Test with real daemon** (once merged)
7. [ ] **Write integration tests** in libvpnmanager

**Deliverable**: ProtonVPNAdapter functional with real Proton VPN

---

## 📊 Estimated Timeline

| Phase | Duration | Dependencies |
|-------|----------|--------------|
| Analysis | 1 week | Understanding codebase |
| Prototype | 1 week | Analysis done |
| Review | 1 week | Prototype ready |
| Implementation | 4 weeks | Approval |
| Integration | 1 week | Daemon merged |
| **Total** | **8 weeks** | **Proton team cooperation** |

---

## 🔄 Alternative Approaches

### Alternative 1: Fork with Patched Daemon

If Proton team is unresponsive or rejects the PR:

1. [ ] Create our own fork of proton-vpn-api-core
2. [ ] Implement MultiTunnelVPNConnector in fork
3. [ ] Use fork in our CLI package
4. [ ] Ship instructions for users to install forked daemon

**Drawbacks**:
- Fork maintenance burden
- Security updates need porting
- Not sustainable long-term
- May conflict with official packages

### Alternative 2: Monkey-Patching

If daemon doesn't need modification but just needs to be used differently:

1. [ ] Could we subclass and override local agent behavior?
2. [ ] Could we use existing API in unintended way?

**Likely not** - local agent hardcodes TUN name.

### Alternative 3: Multiple Daemon Instances

Run separate proton-vpn-local-agent instances on different D-Bus session buses:

1. [ ] Each tunnel: start separate daemon with unique TUN name
2. [ ] Use different `DBUS_SESSION_BUS_ADDRESS` for each
3. [ ] Complex session management
4. [ ] Port conflicts (all daemons want same port?)
5. [ ] Not recommended

---

## 🎯 Success Criteria

Daemon changes complete when:
- [ ] MultiTunnelVPNConnector implemented and tested
- [ ] Local agent accepts custom TUN device name
- [ ] VPNConnection exposes get_tun_device_name()
- [ ] Multiple concurrent connections work simultaneously
- [ ] Each connection has unique TUN (proton0, proton1, ...)
- [ ] Existing single-tunnel use case still works (backward compat)
- [ ] All existing tests still pass
- [ ] New unit tests cover multi-tunnel scenarios
- [ ] Integration tests validate real namespaces
- [ ] PR accepted and merged to upstream (or approved fork)

---

## 📞 Communication with Proton Team

### Initial Contact

**Goal**: Get buy-in and schedule review

**Materials to prepare**:
- [ ] ADAPTER_INTEGRATION.md (already written)
- [ ] MULTITUNNEL Connector_Design.md (already written)
- [ ] PROTON_API_ANALYSIS.md (if not done, create it)
- [ ] Working PoC (this repository proves the approach)
- [ ] This plan (TODO-proton-daemon.md)

**Approach**:
1. Open issue on proton-vpn-api-core: "Feature request: Multi-tunnel support"
2. Explain use case: concurrent multiple VPNs
3. Share our design documents and implementation
4. Ask for feedback and willingness to accept PR
5. Offer to co-develop if helpful

### If They Say No

**Questions to ask**:
- Why? (Technical constraints? Resource constraints? Product decision?)
- Are they working on multi-tunnel themselves? Timeline?
- Can they review a design?
- Would they accept a maintained fork?
- Could they expose an extension point?

**If resource constraints**: Offer to do the work (we already did design)
**If technical constraints**: Discuss alternatives - can we solve differently?
**If product decision**: Understand the reasoning; maybe we're solving wrong problem

---

## 🐛 Risks

1. **Daemon team unavailable** - May take weeks to get response
   - Mitigation: Find contact, schedule meeting, use business channels

2. **PR rejected on design grounds** - They may have different vision
   - Mitigation: Ask for requirements, adapt our design, be flexible

3. **Implementation harder than expected** - Local agent may have complex TUN handling
   - Mitigation: Prototype first, spike on hard parts, ask for help

4. **Tests fail due to complexity** - Multi-threading, race conditions
   - Mitigation: Write simple tests first, add complex scenarios later

5. **API changes needed in multiple places** - More invasive than anticipated
   - Mitigation: Document all changes, minimize surface area, maintain backward compat

6. **Security concerns** - Multiple TUNs might introduce vulnerabilities
   - Mitigation: Review security model, involve security team, isolate namespaces properly

---

## 📚 References

In this repository:
- `docs/ADAPTER_INTEGRATION.md` - Integration design
- `docs/MULTITUNNEL Connector_Design.md` - Detailed connector design
- `docs/PROTON_API_ANALYSIS.md` - API analysis
- `docs/SPECIFICATION.md` - Full system specification
- `src/libvpnmanager/adapters/proton.py` - ProtonVPNAdapter implementation (stub)

---

## 🔄 Dependencies

This subproject depends on:
- **Access to proton-vpn-api-core repository** (need to clone)
- **Understanding of its codebase** (requires time to study)
- **Proton daemon team review/approval** (blocking)
- **Proton security team sign-off** (might be needed)

This subproject enables:
- **libvpnmanager**: Real Proton adapter integration
- **CLI**: Multi-tunnel commands with real servers
- **Testing**: End-to-end integration tests
- **Packaging**: Production-ready packages

---

## 📊 Checkpoint Milestones

- [ ] **M1**: Analysis complete - Know exact code changes needed
- [ ] **M2**: Prototype fork working (in local test)
- [ ] **M3**: PR submitted to proton-vpn-api-core
- [ ] **M4**: PR approved (or design approved)
- [ ] **M5**: PR merged to upstream main
- [ ] **M6**: ProtonVPNAdapter updated and tested with new API
- [ ] **M7**: End-to-end multi-tunnel demo working

**Critical Path**: M3 → M4 (approval) is the biggest blocker

---

**Conclusion**: This is the highest-priority work after completing libvpnmanager. The design is clear and straightforward. Success depends entirely on Proton daemon team cooperation. Estimated 8 weeks from start to integration, but could be longer if review is slow. Start immediately after libvpnmanager is stable.
