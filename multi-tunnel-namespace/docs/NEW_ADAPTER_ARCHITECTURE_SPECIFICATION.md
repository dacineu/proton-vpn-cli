# New Adapter Architecture Specification

**Date:** 2025-03-20
**Status:** Proposal
**Author:** Claude Code
**Related:** `docs/DBUS_SECURITY_AND_ARCHITECTURE.md`, `ARCHITECTURE.md`

---

## Executive Summary

This specification rearchitects the Multi-Tunnel Manager (MTM) to use **persistent adapter processes** with **direct CLI-to-adapter communication**, while MTM manages adapter lifecycle and privileged network operations.

**Key changes:**
- Adapters run as persistent processes (one per user per adapter type)
- Credentials live only in adapter memory (no disk storage)
- CLI talks directly to adapters after startup
- MTM acts as adapter manager + namespace allocator (not message relay)
- Two-channel architecture: CLI↔Adapter (tunnel ops), Adapter↔MTM (resource allocation)

---

## Problems with Current Architecture

| Issue | Current Behavior | Proposed Solution |
|-------|------------------|-------------------|
| **Session persistence on disk** | Credentials stored as JSON in `~/.local/share/protonvpn/sessions/` | Keep credentials only in adapter process memory |
| **Adapter pooling by session** | One adapter per session_name (multiple sessions = multiple adapters) | One adapter per user per adapter_type (shared across all user's tunnels) |
| **MTM-mediated tunnel ops** | All tunnel commands go through MTM | CLI talks directly to adapter for tunnel operations |
| **Multi-tunnel dependency** | Requires multi-tunnel connector support from VPN API | Single-tunnel adapters can handle multiple tunnels sequentially or via multiple connections |
| **Complex session lifecycle** | Separate login command, session storage, validation | Credentials passed once at adapter spawn; adapter handles session lifetime |

---

## Proposed Architecture

### **Component Diagram**

```
┌─────────┐      ┌─────────────────┐      ┌─────────────────┐
│   CLI   │─────▶│   Adapter       │─────▶│   VPN API       │
│ (per    │      │ Process         │      │ (Proton)        │
│ tunnel) │      │ Creds in mem    │      └─────────────────┘
└─────────┘      └─────────────────┘
       │                │
       │                │ control (namespace allocation)
       │                ▼
       │          ┌─────────────────┐
       │          │   MTM Daemon    │
       │          │ (root, NET_ADMIN)
       │          └─────────────────┘
       │                │
       ▼                ▼
┌───────────────┐  ┌─────────────────┐
│ Other CLI     │  │ System          │
│ processes     │  │ (Linux network  │
│ (optional)    │  │  namespaces,    │
└───────────────┘  │  routing tables)│
                   └─────────────────┘
```

**Legend:**
- Dashed line: Privileged operations (CAP_NET_ADMIN)
- Solid line: Direct communication (Unix socket)

---

## Communication Channels

### **1. CLI ↔ MTM (D-Bus)**
**Purpose:** Adapter lifecycle management only

**Methods:**
- `StartAdapter(adapter_type, credentials)` → `{endpoint: socket_path}`
- `StopAdapter(adapter_type, username)` → `{status: "stopped"}`
- `ListAdapters()` → `[{type, name, requires_credentials, status}]`
- `AdapterInfo(adapter_type, username)` → `{running, tunnel_count, ...}`

**NOT used for:** Tunnel creation, connection, disconnection

---

### **2. CLI ↔ Adapter (Unix Socket)**
**Purpose:** Tunnel operations

**Protocol:** JSON-RPC-like over Unix socket

**Methods:**
- `CreateTunnel(tunnel_name, config)` → `{tunnel: {...}}`
- `DestroyTunnel(tunnel_name)` → `{status: "destroyed"}`
- `ConnectTunnel(tunnel_name)` → `{status: "connected"}`
- `DisconnectTunnel(tunnel_name)` → `{status: "disconnected"}`
- `ListTunnels()` → `[{tunnel_info}, ...]`
- `GetStatus(tunnel_name)` → `{status: "...", stats: {...}}`
- `GetTrafficStats(tunnel_name)` → `{bytes_in, bytes_out}`

**Signals (adapter → cli):**
- `TunnelStateChanged(tunnel_name, old_status, new_status)`
- `TunnelCreated(tunnel_info)`
- `TunnelDestroyed(tunnel_name)`

---

### **3. Adapter ↔ MTM (Control Unix Socket)**
**Purpose:** Privileged resource allocation

**Protocol:** Simple JSON messages

**Adapter → MTM:**
- `Register(session_id, adapter_type, username)` → `{status: "registered"}`
- `AllocateTunnel(tunnel_name, device, gateway, dns)` → `{namespace, status}`
- `ReleaseTunnel(tunnel_name)` → `{status: "released"}`
- `Shutdown()` → `{status: "shutting_down"}`

**MTM → Adapter:**
- `TunnelReady(tunnel_name, namespace, device)` (response to AllocateTunnel)
- `TunnelDestroyed(tunnel_name)` (confirmation)
- `ShutdownAck()` (acknowledge shutdown)

---

## Detailed Flow: Creating a Tunnel

### **Scenario A: Adapter Not Running (First Tunnel)**

```bash
$ protonvpn tunnel create work1 --adapter proton --country US --protocol wireguard
```

**Step 1: CLI prompts for credentials** (adapter requires_login=true)
```
VPN Username: user@proton.me
VPN Password: ********
2FA Code (if required): 123456
```

**Step 2: CLI → MTM (D-Bus): StartAdapter**
```json
{
  "adapter_type": "proton",
  "credentials": {
    "username": "user@proton.me",
    "password": "********",
    "twofa": "123456"
  }
}
```

**Step 3: MTM spawns adapter process**
```python
# MTM creates Unix sockets
adapter_socket = "/run/mtm/adapters/user_proton.sock"
control_socket = "/run/mtm/control/user_proton.sock"

env = {
    "ADAPTER_ENDPOINT": adapter_socket,
    "CONTROL_ENDPOINT": control_socket,
    "VPN_USERNAME": "user@proton.me",
    "VPN_PASSWORD": "********",
    "VPN_2FA": "123456",
}

process = await asyncio.create_subprocess_exec(
    "mtm-adapter-proton",
    env=env
)

# Wait for adapter to bind adapter_socket (indicates ready)
await wait_for_socket(adapter_socket, timeout=10)

return {
    "status": "started",
    "endpoint": f"unix://{adapter_socket}"
}
```

**Step 4: Adapter process starts**

```python
# mtm-adapter-proton (cli.py)
async def main():
    # Read env
    adapter_sock = os.getenv("ADAPTER_ENDPOINT")
    control_sock = os.getenv("CONTROL_ENDPOINT")
    vpn_username = os.getenv("VPN_USERNAME")
    vpn_password = os.getenv("VPN_PASSWORD")
    vpn_2fa = os.getenv("VPN_2FA")

    # Start CLI server
    server = await asyncio.start_unix_server(handle_cli, adapter_sock)
    os.chmod(adapter_sock, 0o600)

    # Connect to MTM control socket
    ctrl_reader, ctrl_writer = await asyncio.open_unix_connection(control_sock)

    # Login to VPN (once, at startup)
    global_vpn_session = await proton_login(vpn_username, vpn_password, vpn_2fa)
    print("[proton] Logged in as user@proton.me")

    # Register with MTM
    await send_json(ctrl_writer, {
        "action": "register",
        "session_id": f"{vpn_username}_proton",
        "status": "ready"
    })

    # Serve forever
    async with server:
        await asyncio.gather(
            server.serve_forever(),
            handle_control_messages(ctrl_reader, ctrl_writer)
        )
```

**Step 5: CLI receives adapter endpoint, connects directly**

```python
# CLI (tunnel.py)
adapter_socket = adapter_info["endpoint"]  # from MTM StartAdapter response
adapter_client = AdapterClient(adapter_socket)
await adapter_client.connect()
```

**Step 6: CLI → Adapter: CreateTunnel**

```json
{
  "action": "create_tunnel",
  "tunnel_name": "work1",
  "config": {
    "country": "US",
    "protocol": "wireguard"
  }
}
```

**Step 7: Adapter receives request, connects to VPN**

```python
async def handle_cli(reader, writer):
    msg = await read_json(reader)

    if msg["action"] == "create_tunnel":
        tunnel_name = msg["tunnel_name"]
        config = msg["config"]

        # Use global_vpn_session (from startup) to create connection
        connection = await global_vpn_session.connect(
            tunnel_name=tunnel_name,
            server=find_server(country=config["country"]),
            protocol=config["protocol"]
        )

        # Wait for connection
        await wait_for_state(connection, CONNECTED)

        # Extract info
        tunnel_info = {
            "device": connection.get_interface_name(),  # "tun0"
            "gateway": connection.get_gateway(),
            "dns": connection.get_dns_servers(),
            "endpoint": connection.get_endpoint(),
        }

        # Request namespace from MTM (control channel)
        await send_json(ctrl_writer, {
            "action": "AllocateTunnel",
            "tunnel_name": tunnel_name,
            "device": tunnel_info["device"],
            "gateway": tunnel_info["gateway"],
            "dns": tunnel_info["dns"]
        })

        # Wait for MTM response
        response = await read_json(ctrl_reader)
        if response["status"] == "allocated":
            namespace = response["namespace"]
            tunnel_info["namespace"] = namespace

            # Store tunnel in adapter's tracking dict
            self.tunnels[tunnel_name] = {
                "connection": connection,
                "info": tunnel_info
            }

            # Respond to CLI
            await send_json(writer, {
                "status": "connected",
                "tunnel": {
                    "name": tunnel_name,
                    "device": tunnel_info["device"],
                    "namespace": namespace,
                    "endpoint": tunnel_info["endpoint"]
                }
            })

            print(f"[proton] Tunnel {tunnel_name} connected on {tunnel_info['device']}")
```

**Step 8: MTM allocates namespace**

```python
async def handle_adapter_control(reader, writer):
    msg = await read_json(reader)

    if msg["action"] == "AllocateTunnel":
        tunnel_name = msg["tunnel_name"]
        device = msg["device"]
        namespace = f"vpn_{tunnel_name}"

        # Create network namespace (requires root)
        await run_ip(["netns", "add", namespace])

        # Move device into namespace
        await run_ip(["link", "set", device, "netns", namespace])

        # Configure network inside namespace
        await run_ip(["netns", "exec", namespace,
                      "ip", "addr", "add", f"{msg['gateway']}/24", "dev", device])
        await run_ip(["netns", "exec", namespace,
                      "ip", "link", "set", device, "up"])
        await run_ip(["netns", "exec", namespace,
                      "ip", "route", "add", "default", "via", msg["gateway"]])

        # DNS: write resolv.conf or use resolvconf
        await configure_namespace_dns(namespace, msg["dns"])

        # Respond to adapter
        await send_json(writer, {
            "status": "allocated",
            "namespace": namespace,
            "device": device
        })

        print(f"[MTM] Allocated namespace {namespace} for {device}")
```

**Step 9: CLI receives tunnel info, displays to user**

```python
# CLI receives:
{
  "status": "connected",
  "tunnel": {
    "name": "work1",
    "device": "tun0",
    "namespace": "vpn_work1",
    "endpoint": "se1-01.proton.me:443"
  }
}

print(f"✓ Tunnel '{tunnel_name}' connected")
print(f"  Device: {tunnel['device']}")
print(f"  Namespace: {tunnel['namespace']}")
print(f"  Endpoint: {tunnel['endpoint']}")
```

---

### **Scenario B: Adapter Already Running (Second Tunnel)**

```bash
$ protonvpn tunnel create personal1 --adapter proton --country DE --protocol openvpn-tcp
```

**No credential prompts** - adapter already running with credentials in memory.

**Flow:**

1. CLI → MTM: `StartAdapter(adapter_type="proton", credentials=null)`
2. MTM sees `(proton, user@proton.me)` already running → `{status: "already_running", endpoint: "unix:///run/mtm/adapters/user_proton.sock"}`
3. CLI connects directly to that endpoint (same socket as before)
4. CLI → Adapter: `CreateTunnel(personal1, {country: "DE", protocol: "openvpn-tcp"})`
5. Adapter uses same `global_vpn_session` to create second connection
6. Adapter → MTM: `AllocateTunnel(personal1, device="tun1", ...)`
7. MTM creates namespace `vpn_personal1`, moves tun1, configures
8. Adapter responds to CLI with tunnel info

**Result:** User has two tunnels (work1, personal1) using same adapter process and same VPN session (tokens reused).

---

## Adapter Lifecycle

### **Startup**
1. MTM spawns process with env: `ADAPTER_ENDPOINT`, `CONTROL_ENDPOINT`, credentials
2. Adapter binds CLI server socket (Unix socket, 0600)
3. Adapter connects to MTM control socket
4. Adapter logs in to VPN service (stores session in global memory)
5. Adapter sends `Register` to MTM
6. Adapter begins serving CLI requests

### **Runtime**
- Adapter accepts multiple CLI connections (or one persistent connection)
- Each CLI can create multiple tunnels
- Adapter tracks: `self.tunnels[tunnel_name] = {connection, info}`
- Adapter monitors VPN connections (reconnect logic, health checks)
- If VPN tokens expire, adapter can refresh (if refresh_token available) or exit with error

### **Shutdown**
**When?**
- User calls `protonvpn adapter stop proton` (explicit)
- Adapter process crashes (MTM notices, removes from pool)
- Daemon shutdown (MTM sends `Shutdown` to all adapters)
- Idle timeout (configurable: kill after N minutes with no tunnels)

**Shutdown sequence:**
1. MTM → Adapter (control): `Shutdown()`
2. Adapter → MTM: `ShutdownAck()`
3. Adapter disconnects all tunnels (graceful)
4. Adapter closes sockets, exits
5. MTM removes from `adapter_pool`
6. MTM cleans up any remaining namespaces (optional)

---

## Data Structures

### **MTM AdapterPool**

```python
class AdapterProcess:
    def __init__(self, process, endpoint, control_endpoint, username, adapter_type):
        self.process = subprocess.Process
        self.endpoint = "unix:///path/to/adapter.sock"  # CLI connects here
        self.control_endpoint = "/run/mtm/control/xxx.sock"  # Adapter→MTM
        self.username = username  # OS user who started it
        self.adapter_type = adapter_type
        self.session_id = f"{username}_{adapter_type}"
        self.tunnels: Dict[str, Tunnel] = {}  # tunnel_name → Tunnel (MTM's view)
        self.started_at = datetime
        self.last_activity = datetime

class Daemon:
    def __init__(self):
        # Key: (adapter_type, username)
        self.adapter_pool: Dict[Tuple[str, str], AdapterProcess] = {}
```

---

### **Adapter Internal State**

```python
class Adapter:
    def __init__(self):
        self.vpn_session: Optional[VPNSession] = None  # Credentials, tokens
        self.tunnels: Dict[str, VPNConnection] = {}  # tunnel_name → connection
        self.cli_connections: List[StreamWriter] = []  # Active CLI clients
        self.control_writer: Optional[StreamWriter] = None  # To MTM
        self.adapter_type: str = ""
        self.username: str = ""
```

---

## Security Considerations

### **Credential Passing**

**Current proposal:** Environment variables (`VPN_USERNAME`, `VPN_PASSWORD`, `VPN_2FA`)

**Risks:**
- Visible in `/proc/<pid>/environ` to root users
- May appear in process listing tools
- Left in memory until process exits (can't be cleared from environment)

**Better alternatives:**
1. **stdin on startup:** MTM writes credentials to adapter's stdin, adapter reads once, clears buffer
2. **Ephemeral key exchange:** MTM generates random session key, sends to adapter via control socket after spawn; future messages encrypted
3. **Credential helper:** Use OS keyring (but we explicitly don't want persistence)

**Recommendation:** Use **stdin** for initial credential delivery. It's simple and not visible in `/proc`.

---

### **Socket Permissions**

**Adapter CLI socket:** `/run/mtm/adapters/{username}_{adapter}.sock`
- Created by MTM (running as root) before spawning adapter
- MTM sets mode `0600`, owned by `root:{username}` or `{username}:{username}`
- Only the user who requested adapter can connect
- If root wants to manage all, can connect as root

**MTM control socket:** `/run/mtm/control.sock`
- Created by MTM (root)
- Mode `0600`, owned by `root`
- Only adapter processes (spawned by MTM) can connect (MTM verifies peer credentials)

---

### **Authentication to MTM**

When adapter connects to MTM's control socket, MTM should:
1. Get peer credentials via `SO_PEERCRED` (Linux)
2. Verify that peer's UID matches the `username` claimed in `Register` message
3. Reject mismatches (prevents impersonation)

---

## Changes Required

### **Files to Create/Modify**

#### 1. `daemon/daemon.py` (heavily modified)
- Remove `SessionManager` usage
- Add `AdapterProcessPool` class
- Add `StartAdapter()` D-Bus method
- Add `StopAdapter()` D-Bus method
- Replace `_spawn_adapter()` with new spawn logic (two sockets)
- Add control socket server (`asyncio.start_unix_server`)
- Remove `create_tunnel`, `connect_tunnel` etc. from D-Bus interface? (or keep for legacy)
- Add adapter state tracking (`adapter_pool`)

#### 2. `libvpnmanager/sessions/` (deprecated)
- Remove or mark deprecated
- No longer used for credential storage
- Could keep for WireGuard config file lookup only

#### 3. `adapters/proton_vpn_adapter/cli.py` (new file)
- Create new CLI entrypoint that:
  - Reads env vars for credentials and sockets
  - Binds adapter Unix socket for CLI connections
  - Connects to MTM control socket
  - Logs in to Proton (stores session in memory)
  - Registers with MTM
  - Serves CLI requests and control messages concurrently
- Keep existing `adapter.py` mostly unchanged (just moves credentials to global state)

#### 4. `adapters/proton_vpn_adapter/adapter.py` (modified)
- Change `__init__` to accept optional session (but can also load from global)
- Separate `login()` from `connect()`
- Store `self.session` as class/global variable accessible to all instances in same process
- Add `tunnel_registry` for tracking multiple tunnels

#### 5. `libvpnmanager/client.py` and `dbus/client.py` (modified)
- `ManagerClient` gains `start_adapter(adapter_type, credentials)` method
- `create_tunnel()` changes to:
  1. Call `start_adapter()` if not already running
  2. Get adapter endpoint
  3. Connect to adapter directly (not via MTM D-Bus)
  4. Call adapter's `create_tunnel`
  5. Return result
- Or split into `AdapterClient` class separate from `ManagerClient`

#### 6. `cli/tunnel.py` (modified)
- `create` command:
  - Checks if adapter needs credentials (via `ListAdapters` or `adapter_info`)
  - If needed and not provided, prompts interactively
  - Calls `client.start_adapter(adapter_type, credentials)`
  - Creates `AdapterClient` with returned endpoint
  - Calls `adapter_client.create_tunnel(...)`
  - Displays result
- Add `adapter` subcommand group:
  - `protonvpn adapter list`
  - `protonvpn adapter start proton --username ...`
  - `protonvpn adapter stop proton`

#### 7. `libvpnmanager/adapters/base.py`
- Add `login(credentials)` abstract method to `VPNAdapter`
- Ensure `connect()` doesn't require credentials (assumes already logged in)
- Adapter base class manages multiple tunnels via `_connections` dict (already exists)

---

## Migration Path (Legacy Support)

Keep old D-Bus API working alongside new for backward compatibility:

1. **Old flow** (`CreateTunnel`, `ConnectTunnel` via MTM) → still works
   - MTM internally calls `StartAdapter()` if needed
   - MTM forwards tunnel requests to appropriate adapter via control socket
   - User sees no difference

2. **New flow** (direct adapter) → more efficient, no MTM bottleneck

3. **Deprecation plan:**
   - Phase 1: Both APIs work
   - Phase 2: Old API logs warning
   - Phase 3: Old API removed

---

## Open Questions

1. **How does CLI discover adapter requirements?** (`requires_credentials`)
   - MTM `ListAdapters()` returns adapter metadata including `requires_login`
   - CLI shows adapter selection with login indicator

2. **How to handle 2FA challenges?**
   - Proton may require 2FA on first login from new device
   - Adapter should emit `Need2FA` signal to MTM → CLI?
   - Or handle interactively at spawn (current design: credentials passed upfront)

3. **What if VPN session expires mid-tunnel?**
   - Adapter detects via API error
   - Adapter can attempt refresh with stored refresh_token (if available in memory)
   - If refresh fails, adapter:
     - Disconnects all tunnels
     - Sends `SessionExpired` to MTM
     - MTM notifies connected CLIs (signals)
     - Adapter stays alive but unauthenticated? Or exits?

4. **Can multiple CLI processes talk to same adapter simultaneously?**
   - Yes, adapter should handle multiple concurrent connections on its Unix socket
   - Each connection independent; adapter serializes access to `self.tunnels` dict
   - Use `asyncio.Lock` in adapter for thread-safety

5. **How to destroy a tunnel?**
   - CLI → Adapter: `DestroyTunnel(tunnel_name)`
   - Adapter disconnects VPN connection
   - Adapter → MTM: `ReleaseTunnel(tunnel_name)`
   - MTM deletes namespace
   - Adapter removes from `self.tunnels`

6. **Where is tunnel state stored?**
   - MTM maintains `adapter.tunnels` dictionary (for listing)
   - Adapter maintains its own `tunnels` dict
   - Both should agree; if adapter crashes, MTM should detect and clean up

7. **How does MTM detect adapter crash?**
   - Monitor `process.returncode` with `await process.wait()` in background task
   - On adapter exit, MTM removes from `adapter_pool`
   - MTM cleans up all tunnels belonging to that adapter (iterate `adapter.tunnels`, delete namespaces)
   - Emit `AdapterCrashed` signal to interested clients?

---

## Advantages

✅ **No credential persistence** - better privacy, no plaintext tokens
✅ **Simpler session model** - one adapter = one user session
✅ **Adapter reuse** - second tunnel uses same adapter (credentials reused)
✅ **Multi-tunnel without special connector** - multiple connections from same VPN session
✅ **Cleaner separation** - MTM only does privileged ops; adapters do protocol logic
✅ **Better failure isolation** - Adapter crash only affects that user's tunnels, not others
✅ **CLI can stay attached** - Adapter can push state changes via signals
✅ **Easier debugging** - Each adapter is separate process; can inspect logs separately

---

## Disadvantages

❌ **More processes** - One adapter per user per type (but fewer than one-per-tunnel)
❌ **MTM still needs to track tunnels** (state duplication)
❌ **Adapter startup cost** (login) paid once per user session, not per tunnel
❌ **Complex multi-process synchronization** (if MTM and adapter state diverge)
❌ **Socket management** (many Unix sockets, cleanup on crash)
❌ **Two communication channels** (CLI→adapter, adapter→MTM) instead of one

---

## Implementation Roadmap (Phases)

### **Phase 1: Core Refactor**
1. Create `AdapterProcess` class in daemon
2. Add `StartAdapter()` D-Bus method
3. Create adapter CLI base class with dual-server pattern
4. Implement control protocol (Register, AllocateTunnel)
5. Test with Dummy adapter first (no credentials, simple tunnel)

### **Phase 2: Adapter Migration**
6. Convert `proton_vpn_adapter/cli.py` to new model
7. Implement credential passing via stdin (not env)
8. Add adapter state tracking (tunnels dict)
9. Handle multiple concurrent CLI connections

### **Phase 3: CLI Changes**
10. Modify `ManagerClient` → add `start_adapter()`, `AdapterClient`
11. Update `tunnel create` command to use new flow
12. Add `adapter` subcommands (list, stop)
13. Interactive credential prompt if `requires_credentials=True`

### **Phase 4: MTM Resource Manager**
14. Implement namespace allocation in daemon (already exists in routing)
15. Add Adapter→MTM control handler
16. Verify namespace cleanup when adapter exits
17. Add idle timeout for adapters (kill after N minutes unused)

### **Phase 5: Polish & Testing**
18. Integration tests: full flow CLI→adapter→MTM→namespace
19. Security audit: socket permissions, credential exposure
20. Error handling: adapter crash, MTM restart
21. Documentation update

---

## Example: Adapter Control Protocol

**Message format:** JSON lines (one JSON object per line)

**Adapter → MTM (AllocateTunnel):**
```json
{
  "action": "AllocateTunnel",
  "session_id": "user_proton",
  "tunnel_name": "work1",
  "device": "tun0",
  "gateway": "10.8.0.1",
  "dns": ["1.1.1.1", "1.0.0.1"]
}
```

**MTM → Adapter (TunnelReady):**
```json
{
  "status": "allocated",
  "namespace": "vpn_work1",
  "device": "tun0"
}
```

**MTM → Adapter (Error):**
```json
{
  "status": "error",
  "error": "Device not found",
  "code": "DEVICE_NOT_FOUND"
}
```

---

## Comparison: Old vs New

| Aspect | Current | Proposed |
|--------|---------|----------|
| **Adapter lifetime** | Per session (from SessionManager) | Per user per adapter type (pooled) |
| **Credential storage** | Disk (JSON) + memory | Memory only (no disk) |
| **Credential lifetime** | Until explicit logout or expiry | Until adapter process exits |
| **Tunnel creation path** | CLI → MTM D-Bus → TunnelManager → Adapter (in-process) | CLI → Adapter socket → Adapter → MTM control socket |
| **Adapter communication** | Direct method calls (same process) | JSON over Unix socket (separate process) |
| **Multi-tunnel support** | Requires multi-tunnel connector | Multiple connections from same VPN session |
| **Login** | Separate `Login` D-Bus call | Credentials passed at `StartAdapter` |
| **Session reuse** | Load from disk by session_name | In-memory only; one adapter per user |
| **MTM responsibility** | Everything | Adapter lifecycle + privileged namespace ops |
| **CLI-Daemon coupling** | Tight (single D-Bus interface) | Loose (CLI talks to adapter, not MTM) |
| **Process model** | MTM inherits adapter code (same process) | MTM spawns separate adapter executables |
| **State recovery** | Reload from disk after restart | No recovery; adapters restart fresh |

---

## Conclusion

This specification transforms MTM from a monolithic daemon into a **process supervisor** with privileged network management, while moving VPN protocol logic into isolated, credential-holding adapter processes. The result is a cleaner security boundary, better user experience (single login per session), and simplified adapter implementation (no disk I/O for sessions).

---

**Next steps:**
1. Review with stakeholders
2. Approve or revise
3. Implement Phase 1 (proof of concept with Dummy adapter)
4. Iterate based on testing

---

*Document version: 1.0*
*Last updated: 2025-03-20*
