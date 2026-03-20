# Architecture Restructure Summary

## New Directory Structure

```
multi-tunnel-namespace/
├── src/
│   ├── core/
│   │   └── libvpnmanager/          # CORE LIBRARY (no service dependencies)
│   │       ├── __init__.py
│   │       ├── manager/            # TunnelManager
│   │       │   ├── __init__.py
│   │       │   ├── tunnel_manager.py
│   │       │   └── manager_v2.py
│   │       ├── routing/            # Network isolation strategies
│   │       │   ├── __init__.py
│   │       │   ├── base.py
│   │       │   └── namespace.py
│   │       ├── sessions/           # Session management (base only)
│   │       │   ├── __init__.py
│   │       │   ├── base.py
│   │       │   └── manager.py
│   │       ├── models/             # Data models & exceptions
│   │       │   ├── __init__.py
│   │       │   ├── tunnel.py
│   │       │   ├── config.py
│   │       │   ├── status.py
│   │       │   └── exceptions.py
│   │       ├── dbus/               # D-Bus service & client
│   │       │   ├── __init__.py
│   │       │   ├── service.py
│   │       │   └── client.py
│   │       ├── adapters/           # Base classes only (ABC)
│   │       │   ├── __init__.py
│   │       │   └── base.py
│   │       └── pyproject.toml
│   │
│   ├── adapters/                   # ADAPTER PACKAGES (one per VPN service)
│   │   ├── proton_vpn_adapter/
│   │   │   ├── __init__.py
│   │   │   ├── adapter.py         # ProtonVPNAdapter
│   │   │   ├── sessions/
│   │   │   │   ├── __init__.py
│   │   │   │   └── proton.py      # ProtonSession
│   │   │   └── pyproject.toml
│   │   ├── psiphon_adapter/
│   │   │   ├── __init__.py
│   │   │   ├── adapter.py         # PsiphonAdapter
│   │   │   ├── sessions/
│   │   │   │   ├── __init__.py
│   │   │   │   └── psiphon.py
│   │   │   └── pyproject.toml
│   │   ├── wireguard_adapter/
│   │   │   ├── __init__.py
│   │   │   ├── adapter.py         # WireGuardAdapter
│   │   │   ├── sessions/
│   │   │   │   ├── __init__.py
│   │   │   │   └── wireguard.py
│   │   │   └── pyproject.toml
│   │   └── dummy_adapter/
│   │       ├── __init__.py
│   │       ├── adapter.py         # DummyAdapter (for testing)
│   │       └── pyproject.toml
│   │
│   ├── daemon/
│   │   └── daemon.py              # Daemon entry point: proton-vpn-manager
│   │
│   ├── clis/                      # CLI PACKAGES (future)
│   │   └── protonvpn/            # Main protonvpn CLI
│   │       ├── __init__.py
│   │       ├── main.py
│   │       ├── commands/
│   │       └── pyproject.toml
│   │
│   └── pyproject.toml             # (may be removed; each package has its own)
│
├── packaging/
│   ├── arch/
│   │   ├── PKGBUILD              # Updated to build daemon with adapters
│   │   └── proton-vpn-manager.install
│   └── systemd/
│       └── usr/lib/systemd/system/proton-vpn-manager.service
│
├── docs/
│   ├── ARCHITECTURE_RESTRUCTURE.md  # Detailed design
│   ├── ARCHITECTURE_UML.md           # UML diagrams
│   ├── RESTRUCTURE_TODO.md           # This restructuring task list
│   └── REASONING.md                  # Design rationale
│
├── build-binaries.sh              # Updated build script
├── proton-vpn-manager.spec        # PyInstaller spec for daemon
└── ... (other files)
```

## Package Dependencies

```
dummy_adapter → libvpnmanager
proton_vpn_adapter → libvpnmanager + proton-core + proton-vpn-api-core + ...
psiphon_adapter → libvpnmanager + (psiphon libs)
wireguard_adapter → libvpnmanager + (wireguard-tools via subprocess)

daemon (proton-vpn-manager) → libvpnmanager + selected adapters
protonvpn CLI → libvpnmanager (D-Bus client) + proton_vpn_adapter (types)
```

## Key Changes

### 1. Core libvpnmanager (moved from `src/libvpnmanager/` to `src/core/libvpnmanager/`)
- Contains ONLY infrastructure, no concrete adapters
- Provides:
  - `TunnelManager`
  - `NetworkNamespaceRouting`
  - `SessionManager` (with registry for session types)
  - `VPNAdapter` ABC
  - `Session` ABC
  - Data models (Tunnel, Configs, Status)
  - Exceptions
  - D-Bus service/client

### 2. Adapters are now separate packages
Each adapter is its own installable Python package:
- `proton_vpn_adapter`
- `psiphon_adapter`
- `wireguard_adapter`
- `dummy_adapter`

Each contains:
- `adapter.py`: Implementation of `VPNAdapter`
- `sessions/`: Concrete `Session` subclasses
- `pyproject.toml`: Package metadata & dependencies

### 3. Daemon uses plugin architecture
`daemon/daemon.py`:
- Dynamically imports available adapter packages (try/except)
- Registers each adapter's session type with `SessionManager`
- Registers each adapter type with `TunnelManager`
- Can be configured via `enabled_adapters` parameter

Example:
```python
async def _register_adapters(self):
    try:
        from proton_vpn_adapter import ProtonVPNAdapter
        self.manager.register_adapter_type("proton", ProtonVPNAdapter)
    except ImportError:
        logger.warning("Proton adapter not available")
```

### 4. Session Manager uses registry pattern
Old: Hardcoded `SESSION_TYPES` dict in `SessionManager`
New: Global registry + `SessionManager.register_adapter()` method

Adapters register their session class on import:
```python
# In proton_vpn_adapter/__init__.py
from libvpnmanager.sessions.manager import register_session_type
register_session_type("proton", ProtonSession)
```

### 5. Build system changes
- `proton-vpn-manager.spec` includes adapters as packages
- `build-binaries.sh` still builds daemon + CLI
- PKGBUILD updated to reflect the new package structure

## Migration from Old Structure

### Old (monolithic):
```
src/libvpnmanager/
├── manager.py          # TunnelManager
├── adapters/
│   ├── base.py
│   ├── proton.py       # Embedded
│   ├── psiphon.py      # Embedded
│   └── wireguard.py    # Embedded
├── sessions/
│   ├── manager.py
│   ├── proton.py       # Embedded
│   ├── psiphon.py      # Embedded
│   └── wireguard.py    # Embedded
└── ...
```

### New (separated):
```
src/core/libvpnmanager/     # Core only, no concrete adapters
├── manager/
├── adapters/base.py        # Only base class
├── sessions/
│   ├── manager.py
│   └── base.py             # Only base class
└── ...

src/adapters/proton_vpn_adapter/   # External package
├── adapter.py
├── sessions/proton.py
└── ...

src/adapters/psiphon_adapter/
├── adapter.py
├── sessions/psiphon.py
└── ...

etc.
```

## Testing the Build

```bash
# 1. Build core libvpnmanager wheel (optional)
cd src/core/libvpnmanager
pip install build
python -m build --wheel

# 2. Build daemon binary (includes all adapters)
cd multi-tunnel-namespace
./build-binaries.sh
# Output: dist/proton-vpn-manager

# 3. Run daemon
sudo dist/proton-vpn-manager
# Should log: "Registered adapter: dummy"
#             "Registered adapter: proton" (if available)
#             "Available adapters: dummy, proton, ..."
```

## Compatibility Notes

- **Backwards compatibility**: The old `libvpnmanager` package is gone. All code must be updated to use the new structure.
- **Adapter loading**: If an adapter package is not installed, it's simply not registered. Daemon still works with remaining adapters.
- **Session persistence**: Session files remain compatible (same format). They're stored in `$XDG_DATA_HOME/protonvpn/sessions/{adapter_type}/`.
- **D-Bus interface**: Unchanged. CLI still talks to daemon via D-Bus.

## Next Steps

1. ✅ Complete file moves and imports
2. ✅ Update daemon for dynamic adapter loading
3. ✅ Create adapter pyproject.toml files
4. ✅ Update build scripts (PKGBUILD, build-binaries.sh)
5. ⏳ Test build on clean system
6. ⏳ Create CLI packages (protonvpn, etc.)
7. ⏳ Update documentation for users and developers
8. ⏳ Write migration guide from old monolithic structure

## Questions?

See detailed docs:
- `ARCHITECTURE_RESTRUCTURE.md` - Full design document
- `ARCHITECTURE_UML.md` - UML diagrams
- `REASONING.md` - Design rationale
