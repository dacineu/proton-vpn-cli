# Architecture Restructure: Reasoning and Design Decisions

## Problem Statement

The original codebase had a monolithic `libvpnmanager` package that contained:
- Core infrastructure (TunnelManager, routing, sessions, models, D-Bus)
- All adapter implementations (Proton, Psiphon, WireGuard, Dummy)

This caused several issues:
1. **Tight coupling**: Adapters were deeply integrated into the core package
2. **Dependency bloat**: Installing libvpnmanager pulled in all adapter dependencies (including heavy proton-vpn-api-core)
3. **Inflexible distribution**: Could not ship the daemon with only selected adapters
4. **Hard to extend**: Third parties couldn't add new adapters without modifying core
5. **Unclear boundaries**: Mixing of generic infrastructure with service-specific code

## Proposed Solution

Separate the codebase into distinct layers with clear dependencies:

```
core/libvpnmanager (no external service deps)
        ↑
        │ depends on
        │
adapters/*_adapter (one per VPN service)
        ↑
        │ each depends on core + service libs
        │
daemon (uses core and loads adapters)
        ↑
        │ talks over D-Bus
        │
CLIs (independent binaries or packages)
```

### Key Principles

1. **Dependency Inversion**: Core defines abstract interfaces (VPNAdapter, Session). Adapters implement them.
2. **Single Responsibility**: Each package has a distinct purpose.
3. **Open/Closed**: New adapters can be added without changing core.
4. **Composition over Inheritance**: TunnelManager composes with adapters via registration.
5. **Plugin Architecture**: Adapters are discovered/registered at runtime.

## Benefits

- **Modularity**: Can ship `proton-vpn-manager` with only `proton_vpn_adapter` and `dummy_adapter` if desired
- **Testability**: Adapters can be mocked/stubbed easily against the ABCs
- **Maintainability**: Clear boundaries mean changes to one adapter don't affect others
- **Extensibility**: Third-party adapters (e.g., `nordvpn-adapter`) can be created as separate packages
- **Dependency hygiene**: Users who only need WireGuard don't need proton-vpn-api-core installed

## Trade-offs

- **Slightly more complex build**: Need to package multiple components
- **More packages**: From 1 package to ~6+ packages (but they can be combined in distro packaging)
- **Initial refactor effort**: Moving code and fixing imports is non-trivial

## Why Not Separate Daemons?

The user explicitly requested: *"no need for separate daemons to reside in memory for different vpn services but just inside the global vpn manager"*.

Thus we maintain:
- **Single daemon process**: `proton-vpn-manager` runs as root and listens on D-Bus
- **Shared adapter instances**: One instance per adapter type, shared across all tunnels
- **Adapter state**: Each adapter may spawn external processes (e.g., wg-quick, proton-vpn-api) that persist independently
- **Daemon restart resilience**: If the daemon restarts, external processes survive and can be reattached (future feature)

## Session Management

- Core defines `Session` abstract base class
- Each adapter provides its own `Session` subclass (`ProtonSession`, `WireGuardSession`, etc.)
- `SessionManager` uses a registry pattern: adapters call `register_session_type()` during import
- Sessions are stored per-user in `$XDG_DATA_HOME/protonvpn/sessions/{adapter_type}/`
- When a tunnel is created, the adapter receives config containing `session_name` and loads credentials from its session

## Adapter Interface

```python
class VPNAdapter(ABC):
    @abstractmethod
    async def connect(config, progress_cb) -> Tunnel: ...

    @abstractmethod
    async def disconnect(tunnel) -> None: ...

    @abstractmethod
    async def get_status(tunnel) -> TunnelStatus: ...

    @abstractmethod
    async def get_traffic_stats(tunnel) -> Tuple[int, int]: ...

    @abstractmethod
    async def cleanup() -> None: ...

    @property
    @abstractmethod
    def capabilities(self) -> AdapterCapabilities: ...
```

Adapters are instantiated with `session_manager`:

```python
adapter = ProtonVPNAdapter(session_manager=sm)
tunnel = await adapter.connect(config, progress_cb)
```

They manage their own external processes/connections and report tunnel state.

## Build Artifacts

With the restructure, building produces:

1. **Standalone daemon binary** (`proton-vpn-manager`):
   - Includes embedded Python interpreter
   - Includes core libvpnmanager + all selected adapters
   - Option A: embed all adapters (default)
   - Option B: embed only those in configuration (via PyInstaller filters)

2. **Adapter wheels** (`proton_vpn_adapter-*.whl`, etc.):
   - Can be installed separately for development or custom deployments
   - Lightweight, just Python code (no interpreter)

3. **CLI binaries** (`protonvpn`):
   - Standalone binary with embedded Python
   - Includes D-Bus client and adapter-specific config types
   - Does NOT include full libvpnmanager (uses D-Bus)

4. **Library wheel** (`libvpnmanager-*.whl`):
   - The core library, for developers or custom setups

## Migration Path

For existing users:

1. Install `proton-vpn-manager` package (daemon) which now includes everything
2. Install `protonvpn` CLI (still standalone)
3. Enable and start `proton-vpn-manager.service`
4. No configuration changes needed for typical setups

For advanced users who want to customize:

- Install individual adapter wheels and configure daemon to load only those
- Write custom adapters by implementing `VPNAdapter` and registering with `SessionManager`

## Future Enhancements

- Adapter discovery via Python entry points (`setuptools` entry points)
- Configuration file (`/etc/protonvpn/daemon.yaml`) to enable/disable adapters
- Hot-reloading of adapters without daemon restart (signal-based)
- Session persistence across daemon restarts (reattach to existing tunnels)

---

## Conclusion

This restructure improves the architecture significantly by separating concerns, reducing coupling, and enabling modular deployment. It aligns with industry best practices for plugin-based systems and sets the stage for future extensibility.
