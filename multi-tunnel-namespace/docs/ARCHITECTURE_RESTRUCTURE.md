# Proposed Architecture Restructuring

## Current Issues

1. **Monolithic libvpnmanager**: Contains both core infrastructure AND all adapters (Proton, Psiphon, WireGuard)
2. **Unclear separation**: Adapters are tightly coupled to the core library
3. **Distribution inefficiency**: Every installation includes all adapters even if only one is used
4. **Dependency bloat**: Proton adapter requires proton-vpn-api-core even if you only want WireGuard

## Proposed Architecture

### High-Level Structure

```
┌─────────────────────────────────────────────────────────────────┐
│                         User/CLI Layer                          │
├─────────────────────────────────────────────────────────────────┤
│  protonvpn CLI    │  psiphon CLI    │  wireguard CLI           │
│  (uses ProtonVPNAdapter) │ (uses PsiphonAdapter) │ ...        │
└───────────────────────────────┬─────────────────────────────────┘
                                │ uses
└───────────────────────────────▼─────────────────────────────────┘
                      ┌─────────────────────┐
                      │   Adapter Library   │
                      │   (per VPN service) │
                      ├─────────────────────┤
                      │  proton-vpn-adapter │
                      │  psiphon-adapter    │
                      │  wireguard-adapter  │
                      └───────────┬─────────┘
                                  │ implements
                      ┌───────────▼─────────┐
                      │  VPNAdapter (ABC)   │
                      │  Defined in:        │
                      │  libvpnmanager      │
                      └───────────┬─────────┘
                                  │
┌─────────────────────────────────▼─────────────────────────────────┐
│                    Core Manager Daemon                           │
│  ┌───────────────────────────────────────────────────────────┐  │
│  │              libvpnmanager (Core Only)                    │  │
│  │  ┌────────────┐  ┌────────────┐  ┌──────────────────┐   │  │
│  │  │ TunnelMgr  │  │ RoutingMgr │  │  SessionManager  │   │  │
│  │  └────────────┘  └────────────┘  └──────────────────┘   │  │
│  │  ┌─────────────────────────────────────────────────────┐ │  │
│  │  │         NetworkNamespaceRouting (Strategy)          │ │  │
│  │  └─────────────────────────────────────────────────────┘ │  │
│  │  ┌─────────────────────────────────────────────────────┐ │  │
│  │  │              D-Bus Service (org.protonvpn)         │ │  │
│  │  └─────────────────────────────────────────────────────┘ │  │
│  └───────────────────────────────────────────────────────────┘  │
└─────────────────────────────────────────────────────────────────┘
                                  │
                    ┌─────────────┴──────────────┐
                    │    System Resources        │
                    ├────────────────────────────┤
                    │ Network Namespaces         │
                    │ TUN Devices                │
                    │ Routing Tables             │
                    │ iptables/nftables          │
                    └────────────────────────────┘
```

### Package Structure

```
multi-tunnel-namespace/  (root repository)
│
├── core/
│   └── libvpnmanager/              # Core manager library (renamed from src/libvpnmanager)
│       ├── __init__.py
│       ├── manager/
│       │   ├── __init__.py
│       │   ├── tunnel_manager.py   # TunnelManager class
│       │   └── exceptions.py
│       ├── routing/
│       │   ├── __init__.py
│       │   ├── base.py             # RoutingStrategy ABC
│       │   └── namespace.py        # NetworkNamespaceRouting
│       ├── sessions/
│       │   ├── __init__.py
│       │   ├── manager.py          # SessionManager
│       │   └── base.py             # Session ABC
│       ├── models/
│       │   ├── __init__.py
│       │   ├── tunnel.py
│       │   ├── config.py
│       │   ├── status.py
│       │   └── exceptions.py       # Shared exception types
│       ├── dbus/
│       │   ├── __init__.py
│       │   ├── service.py          # D-Bus service
│       │   └── client.py           # D-Bus client
│       ├── adapters/
│       │   ├── __init__.py
│       │   ├── base.py             # VPNAdapter ABC + AdapterCapabilities
│       │   └── exceptions.py       # Adapter-specific exceptions
│       └── pyproject.toml          # Package: libvpnmanager
│
├── adapters/
│   ├── proton-vpn-adapter/         # NEW PACKAGE
│   │   ├── __init__.py
│   │   ├── adapter.py              # ProtonVPNAdapter implementation
│   │   ├── sessions/
│   │   │   ├── __init__.py
│   │   │   └── proton.py           # ProtonSession
│   │   ├── proton/                 # Proton-specific utils
│   │   └── pyproject.toml          # Package: proton-vpn-adapter
│   │
│   ├── psiphon-adapter/            # NEW PACKAGE
│   │   ├── __init__.py
│   │   ├── adapter.py
│   │   ├── sessions/
│   │   │   ├── __init__.py
│   │   │   └── psiphon.py
│   │   └── pyproject.toml          # Package: psiphon-adapter
│   │
│   └── wireguard-adapter/          # NEW PACKAGE
│       ├── __init__.py
│       ├── adapter.py
│       ├── sessions/
│       │   ├── __init__.py
│       │   └── wireguard.py
│       └── pyproject.toml          # Package: wireguard-adapter
│
├── daemon/
│   └── daemon.py                   # Entry point: starts D-Bus service
│
├── clis/
│   ├── protonvpn/                  # Proton VPN CLI
│   │   ├── __init__.py
│   │   ├── main.py
│   │   ├── commands/
│   │   │   ├── __init__.py
│   │   │   ├── account.py
│   │   │   ├── tunnel.py
│   │   │   └── ...
│   │   └── pyproject.toml         # Package: protonvpn
│   │
│   ├── psiphon-cli/                # Psiphon CLI (if needed)
│   └── wireguard-cli/              # WireGuard CLI (if needed)
│
├── packaging/
│   ├── arch/
│   │   ├── PKGBUILD.daemon        # Builds daemon with selected adapters
│   │   ├── PKGBUILD.protonvpn-cli
│   │   ├── PKGBUILD.proton-vpn-adapter
│   │   └── ...
│   ├── deb/
│   └── rpm/
│
└── docs/
    ├── ARCHITECTURE_UML.md        # This document
    ├── SEQUENCE_DIAGRAMS.md
    └── ADAPTER_DEVELOPMENT.md     # How to create new adapters
```

## Component Responsibilities

### libvpnmanager (Core)

**Does NOT know about specific VPN services**

Provides:
- `TunnelManager`: Orchestrates tunnel lifecycle, delegates to adapters
- `NetworkNamespaceRouting`: Creates/configures network namespaces
- `SessionManager`: Manages user sessions (load/save/delete)
- `RoutingStrategy` (ABC): Interface for routing implementations
- `VPNAdapter` (ABC): Interface for VPN service adapters
- `D-Bus service`: Exposes `org.protonvpn.Manager` interface
- Data models: `Tunnel`, `ConnectionConfig`, `TunnelStatus`
- Exception hierarchy

**Session Management Philosophy**:
- Core defines `Session` ABC (abstract base class)
- Each adapter provides its own `Session` subclass
- SessionManager stores/loads sessions using adapter-specific serialization
- Sessions contain credentials/tokens needed by the adapter

### Adapter Packages (e.g., proton-vpn-adapter)

**Knows about ONE VPN service**

Depends on:
- `libvpnmanager` (for base classes and manager)
- Service-specific libraries (e.g., `proton-vpn-api-core`)

Provides:
- `ProtonVPNAdapter(VPNAdapter)`: Implements connect/disconnect/status
- `ProtonSession(Session)`: Implements credential storage/loading
- `ProtonConnectionConfig(ConnectionConfig)`: Service-specific config
- Service integration (API clients, protocol handlers)

**Does NOT provide**:
- Network namespace handling (done by core)
- D-Bus interface (done by core)
- CLI commands (done by separate CLI package)

### CLI Packages (e.g., protonvpn)

**User interface layer**

Depends on:
- `libvpnmanager` (for D-Bus client)
- Specific adapter package (e.g., `proton-vpn-adapter`) for config types

Provides:
- Command-line interface (`click` commands)
- User input validation
- Pretty printing (tables, colors)
- Configuration files (user-specific)

Can operate in two modes:
1. **Direct library mode** (if run as root): Import libvpnmanager directly
2. **D-Bus mode** (recommended): Talk to daemon via D-Bus

### Daemon

**System service**

Depends on:
- `libvpnmanager` (core)
- Selected adapter packages (e.g., `proton-vpn-adapter`)

Provides:
- Systemd service: `proton-vpn-manager.service`
- D-Bus service: `org.protonvpn.Manager`
- Runs as root (or with capabilities)
- Loads configured adapters on startup
- Manages global state (all tunnels, all users)

**Configuration**:
- `/etc/protonvpn/daemon.yaml` - List of enabled adapters
- Can dynamically reload adapters without restart

## Data Flow

### Creating a Tunnel (via CLI)

```
User runs: protonvpn tunnel create --server @fastest --protocol wireguard

1. CLI parses arguments → creates ProtonConnectionConfig object
2. CLI calls D-Bus: Manager.CreateTunnel(config_dict, username)
3. Daemon receives call:
   - Validates user permissions
   - TunnelManager.create_tunnel(config, username)
     * Looks up adapter type from config (e.g., "proton")
     * Gets or creates adapter instance (cached per session)
     * Adapter validates config, stores session
     * Returns Tunnel object (not yet connected)
   - Returns tunnel name to CLI
4. CLI calls: Manager.ConnectTunnel(tunnel_name, username)
5. Daemon:
   - TunnelManager.connect_tunnel(tunnel_name, username)
     * Gets adapter for tunnel's (adapter_type, session_name)
     * Calls adapter.connect(config)
       - Adapter uses its library to establish VPN connection
       - Returns connected Tunnel with device name
     * Routing.create_tunnel_context(tunnel_name)
       - Creates network namespace
       - Moves device into namespace
       - Configures routing/DNS
     * Updates Tunnel object
   - Returns success
6. CLI displays tunnel info
```

### Adapter Implementation (Example: Proton)

```python
# proton-vpn-adapter/adapter.py

class ProtonVPNAdapter(VPNAdapter):
    def __init__(self, session_manager):
        self.session_manager = session_manager
        self.api = None

    async def connect(self, config: ProtonConnectionConfig, progress_cb):
        # 1. Load/create session
        session = await self.session_manager.load_session(
            "proton", config.session_name, config.username
        )

        # 2. Initialize API if needed
        if not self.api:
            self.api = ProtonVPNAPI()
            await self.api.login(session.credentials)

        # 3. Establish connection using proton-vpn-api-core
        connection = await self.api.connect(
            server=config.server,
            protocol=config.protocol,
            tunnel_name=config.tunnel_name  # For multi-tunnel support
        )

        # 4. Wait for connection, report progress
        async for status in connection.monitor():
            progress_cb(status.message)

        # 5. Return Tunnel object
        return Tunnel(
            name=config.tunnel_name,
            adapter="proton",
            session_name=config.session_name,
            username=config.username,
            device=connection.get_tun_device(),
            endpoint=connection.get_endpoint(),
            connected_at=datetime.now(),
            metadata={"session_id": connection.id}
        )

    async def disconnect(self, tunnel: Tunnel):
        # Find connection by tunnel name and disconnect
        await self.api.disconnect_tunnel(tunnel.name)

    async def get_status(self, tunnel: Tunnel) -> TunnelStatus:
        connection = self.api.get_connection(tunnel.name)
        return connection.status

    async def cleanup(self):
        if self.api:
            await self.api.logout()
```

## Migration Steps

### Phase 1: Extract Core to libvpnmanager
1. Create `core/libvpnmanager/` structure
2. Move:
   - `manager.py` → `core/libvpnmanager/manager/tunnel_manager.py`
   - `routing/` → `core/libvpnmanager/routing/`
   - `sessions/` (base classes only) → `core/libvpnmanager/sessions/`
   - `models/` → `core/libvpnmanager/models/`
   - `dbus/` → `core/libvpnmanager/dbus/`
   - `adapters/base.py` → `core/libvpnmanager/adapters/base.py`
3. Keep concrete adapters in place temporarily for backward compatibility
4. Update imports throughout

### Phase 2: Create Adapter Packages
1. For each adapter (Proton, Psiphon, WireGuard):
   - Create new directory: `adapters/proton-vpn-adapter/`
   - Move:
     - `adapters/proton.py` → `adapters/proton-vpn-adapter/adapter.py`
     - `sessions/proton.py` → `adapters/proton-vpn-adapter/sessions/proton.py`
   - Update imports to import from `libvpnmanager`
   - Create `pyproject.toml` with proper dependencies
   - Make it installable via pip

2. Update daemon to dynamically import adapters based on config

### Phase 3: Update Daemon
1. Modify `daemon/daemon.py`:
```python
async def start(self):
    # Load core manager
    routing = NetworkNamespaceRouting()
    self.manager = TunnelManager(routing)

    # Load adapters from config
    adapter_configs = load_daemon_config()  # e.g., ["proton", "wireguard"]
    for adapter_name in adapter_configs:
        if adapter_name == "proton":
            from proton_vpn_adapter import ProtonVPNAdapter
            adapter = ProtonVPNAdapter(self.manager.session_manager)
            self.manager.register_adapter(adapter)  # New method
        elif adapter_name == "wireguard":
            from wireguard_adapter import WireGuardAdapter
            adapter = WireGuardAdapter(self.manager.session_manager)
            self.manager.register_adapter(adapter)

    # Start D-Bus service
    await start_service(self.manager)
```

### Phase 4: Update CLI
1. CLI packages depend on:
   - `libvpnmanager` (for D-Bus client)
   - Specific adapter (for config types)
2. CLI no longer includes adapter code directly
3. Example:
```python
# protonvpn/commands/tunnel.py

from libvpnmanager.dbus.client import get_client
from proton_vpn_adapter import ProtonConnectionConfig

@cli.command()
def create(server, protocol, session):
    config = ProtonConnectionConfig(
        server=server, protocol=protocol, session_name=session
    )
    client = get_client()
    tunnel = client.create_tunnel(config, getpass.getuser())
    ...
```

### Phase 5: Update Packaging
1. **Daemon package**:
   - Includes: libvpnmanager core + selected adapters
   - One package that can be customized per distro

2. **CLI packages**:
   - `protonvpn` - depends on `libvpnmanager` + `proton-vpn-adapter`
   - Each CLI is separate

3. **Adapter packages** (installable separately):
   - `proton-vpn-adapter` - for third-party tooling
   - `wireguard-adapter`
   - `psiphon-adapter`

## Benefits

1. **Clear separation**: Core knows nothing about specific VPN services
2. **Modular distribution**: Can ship daemon with only needed adapters
3. **Testability**: Each adapter can be tested independently
4. **Extensibility**: Third parties can create adapters without touching core
5. **Reduced dependencies**: Install only what you need
6. **Single daemon**: All VPN services managed by one process (no memory bloat)
7. **Standardized interface**: All adapters follow same ABC

## Compatibility Considerations

- **Backward compatibility**: Keep old `libvpnmanager` package as meta-package that includes all adapters
- **Migration path**: Provide both monolithic and split packages for 1-2 releases
- **Adapter discovery**: Use Python entry points or config file for dynamic loading
- **Versioning**: Core and adapters version independently (semantic versioning)

## UML Diagrams

See following sections for:
1. **Class Diagram**: Package structure and relationships
2. **Sequence Diagram**: Tunnel creation flow
3. **Component Diagram**: Runtime architecture

## Risks & Mitigation

| Risk | Mitigation |
|------|------------|
| Breaking existing integrations | Keep compatibility package, deprecation warnings |
| Adapter interface changes | Stable ABC, versioned interfaces |
| Performance overhead from indirection | Minimal (adapter is just one method call) |
| Configuration complexity | Sensible defaults, auto-detection |

## Next Steps

1. Get approval on architecture
2. Implement Phase 1 (extract core)
3. Write adapter interface tests (contract tests)
4. Implement Phase 2 (split adapters)
5. Update daemon and packaging
6. Update documentation
7. Migration guide for existing users
