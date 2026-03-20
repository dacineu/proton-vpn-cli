# Architecture Analysis

## Architectural Pattern

**Two-Tier Daemon Architecture with Adapter Pattern**

The system implements a multi-process, multi-adapter VPN management platform with strong isolation boundaries:

```
CLI/Client → MTM Daemon (IPC) → Adapter Processes (network namespaces)
```

### Core Components

#### 1. MTM Daemon (`daemon/daemon.py`)
- Main service orchestrator (entry point: `proton-vpn-manager`)
- Manages lifecycle of adapter subprocesses
- Provides IPC interface to clients (D-Bus, Unix socket, WebSocket)
- Coordinates network resource allocation via `ResourceAllocator`
- Uses `AdapterRegistry` to discover available adapters
- Maintains `SessionManager` for multi-user support

**Key responsibilities:**
- Spawn/stop adapter processes per session
- Allocate/release network namespaces and routing
- Authenticate/authorize client requests
- Tunnel state tracking and coordination

#### 2. Adapter Layer (`adapters/*/`)
- Each adapter is a standalone executable (`mtm-adapter-*`)
- Runs in its own process, managed by daemon
- Implements protocol-specific tunnel control (Proton, Psiphon, WireGuard, Dummy)
- Communicates with daemon via internal Unix socket for resource allocation
- Direct client control via separate Unix socket for tunnel operations

**Adapter structure:**
```
adapter.py    - Core adapter logic (inherits from libvpnmanager.adapters.base.VPNAdapter)
cli.py        - Entry point, process lifecycle, socket server
sessions/     - State persistence and session-specific logic
pyproject.toml - Adapter-specific dependencies
```

#### 3. Core Library (`libvpnmanager/`)
Shared codebase used by daemon and adapters:

- **`manager.py`** (`TunnelManager`) - High-level orchestrator (usable standalone)
- **`client.py`** - Client library for connecting to MTM daemon
- **`adapters/`**
  - `base.py` - Abstract `VPNAdapter` base class
  - `proton.py`, `dummy.py`, `remote.py`, `remote_runner.py`, `unix_adapter_server.py` - Adapter implementations
- **`models/`**
  - `config.py` - Configuration models (Pydantic)
  - `tunnel.py` - Tunnel state models
  - `status.py` - Status reporting
  - `exceptions.py` - Exception hierarchy
- **`sessions/`**
  - `manager.py`, `base.py`, `dummy.py` + protocol-specific session modules
- **`routing/`**
  - `base.py` - Abstract routing strategy
  - `namespace.py` - Network namespace implementation using pyroute2
- **`ipc/`**
  - `dbus.py` - D-Bus transport
  - `unix_socket.py` - Unix socket transport
  - `websocket.py` - WebSocket transport
  - `transport.py` - Abstraction layer
- **`dbus/`**
  - `service.py` - D-Bus service registration
  - `client.py` - D-Bus client proxy

#### 4. CLI Layer (`cli/`)
- `cli/tunnel.py` - Command-line interface for tunnel management
- Entry points for user-facing commands

#### 5. Resource Management
- `daemon/resource_allocator.py` - Allocates network resources (namespaces, routing)
- `daemon/adapter_registry.py` - Discovers and registers adapter types

## Data Flow

### Tunnel Creation Flow

1. Client sends `create_tunnel` request to daemon via IPC
2. Daemon authenticates user, checks authorization
3. Daemon creates/locks network namespace via `ResourceAllocator`
4. Daemon spawns adapter subprocess for requested VPN type
5. Adapter connects to daemon's internal socket to claim namespace
6. Adapter performs VPN connection (protocol-specific)
7. Daemon returns tunnel endpoint info to client

### Tunnel Operation Flow

1. Client sends tunnel commands (`connect`, `disconnect`, `status`) to daemon
2. Daemon routes to appropriate adapter (via session lookup)
3. Adapter executes command, returns result
4. Daemon updates tunnel state, notifies interested clients via signals

### Multi-User Support

- Each user can own multiple sessions
- Sessions isolate adapter instances per user
- Admin users can list/operate on all users' tunnels
- File system permissions and group membership enforce access control

## Design Patterns

- **Adapter Pattern** - Each VPN protocol encapsulated in adapter class
- **Factory Pattern** - Adapter instantiation via registry
- **Strategy Pattern** - Routing strategies (`RoutingStrategy` interface)
- **Singleton/Registry** - `AdapterRegistry`, `SessionManager`
- **Command Pattern** - IPC messages as commands
- **Observer Pattern** - Status signals broadcast to clients
- **Resource Allocation** - Allocation/claim pattern between daemon and adapters

## Concurrency Model

- **Async I/O** - All components built on `asyncio`
- **Process Isolation** - Each adapter runs in separate OS process
- **Thread Safety** - `TunnelManager` uses `asyncio.Lock` for shared state
- **Lock-free reads** - Tunnel lookups mostly read-only

## Extension Points

### Adding a New Adapter

1. Create `adapters/new_adapter/` with:
   - `adapter.py` implementing `VPNAdapter` abstract methods
   - `cli.py` with Unix socket server for daemon control
   - `sessions/` for state persistence (optional)
   - `pyproject.toml` with adapter dependencies
2. Register adapter in `daemon/ADAPTER_CAPABILITIES`
3. Ensure adapter executable discoverable via PATH or `MTM_ADAPTER_DIR`

### Adding a New Transport

1. Implement `ipc.Transport` interface in new module
2. Add factory function to `ipc/__init__.py`
3. Update `list_transports()` and `get_server_transport()`

### Custom Routing Strategies

1. Implement `routing.base.RoutingStrategy` interface
2. Override network namespace creation, interface setup, routing rules
3. Configure daemon to use custom strategy

## Security Model

- **Process isolation** - Adapters run as separate processes (potential for privilege separation)
- **Network namespace isolation** - Each tunnel gets isolated network stack
- **User authorization** - Group-based admin detection (`sudo`, `wheel`, `admin`, `adm`)
- **Socket permissions** - Unix socket access control via filesystem perms
- **Input validation** - Pydantic models for all external data
- **Capability advertising** - Adapters declare capabilities, daemon enforces limits

## Error Handling

- Exception hierarchy defined in `models/exceptions.py`
- Adapter errors reported via exceptions, propagated to clients
- Daemon handles adapter crashes, cleans up resources
- Graceful shutdown via signal handling

---

*Generated by codebase mapper (arch focus)*
