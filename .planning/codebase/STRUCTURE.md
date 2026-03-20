# Codebase Structure

## Repository Layout

```
.
├── multi-tunnel-namespace/          # Main Python package (Python 3.9+)
│   ├── src/                        # Source code (src layout)
│   │   ├── adapters/               # VPN adapter implementations
│   │   │   ├── dummy_adapter/
│   │   │   ├── proton_vpn_adapter/
│   │   │   ├── psiphon_adapter/
│   │   │   └── wireguard_adapter/
│   │   ├── cli/                    # Command-line interface
│   │   │   └── tunnel.py
│   │   ├── daemon/                 # MTM daemon
│   │   │   ├── daemon.py          # Main daemon class (VPNDaemon)
│   │   │   ├── daemon_b.py        # Alternative/boot daemon variant?
│   │   │   ├── adapter_registry.py
│   │   │   └── resource_allocator.py
│   │   ├── libvpnmanager/          # Core library
│   │   │   ├── adapters/           # Adapter base classes & utilities
│   │   │   │   ├── base.py        # VPNAdapter abstract base
│   │   │   │   ├── proton.py      # Proton-specific adapter
│   │   │   │   ├── dummy.py       # Dummy adapter
│   │   │   │   ├── remote.py      # Remote adapter client
│   │   │   │   ├── remote_runner.py
│   │   │   │   ├── unix_adapter_server.py
│   │   │   │   └── __init__.py
│   │   │   ├── client.py          # Daemon client
│   │   │   ├── manager.py         # TunnelManager (orchestrator)
│   │   │   ├── manager_v2.py
│   │   │   ├── dbus/              # D-Bus service/client
│   │   │   ├── ipc/               # Transport layer (dbus, unix, websocket)
│   │   │   ├── models/            # Pydantic data models
│   │   │   │   ├── config.py
│   │   │   │   ├── tunnel.py
│   │   │   │   ├── status.py
│   │   │   │   ├── exceptions.py
│   │   │   │   └── __init__.py
│   │   │   ├── routing/           # Network namespace & routing
│   │   │   │   ├── base.py        # RoutingStrategy ABC
│   │   │   │   ├── namespace.py   # NetworkNamespaceRouting
│   │   │   │   └── __init__.py
│   │   │   ├── sessions/          # Session management
│   │   │   │   ├── manager.py
│   │   │   │   ├── base.py
│   │   │   │   ├── dummy.py
│   │   │   │   ├── proton.py
│   │   │   │   ├── psiphon.py
│   │   │   │   ├── wireguard.py
│   │   │   │   └── __init__.py
│   │   │   ├── README.md
│   │   │   └── py.typed
│   │   ├── pyproject.toml         # Package config, dependencies, tool settings
│   │   └── __init__.py
│   ├── tests/                      # Unit and integration tests
│   │   └── unit/
│   ├── examples/                   # Usage examples
│   │   └── 02_library_integration_test.py
│   ├── docs/                       # Documentation
│   │   ├── ARCHITECTURE_RESTRUCTURE.md
│   │   ├── ARCHITECTURE_UML.md
│   │   ├── DBUS_SECURITY_AND_ARCHITECTURE.md
│   │   ├── REASONING.md
│   │   ├── RESTRUCTURE_COMPLETE_SUMMARY.md
│   │   └── RESTRUCTURE_TODO.md
│   ├── packaging/                  # Build and package scripts
│   │   ├── arch/                   # Arch Linux PKGBUILD and helpers
│   │   │   ├── PKGBUILD
│   │   │   ├── PKGBUILD.local
│   │   │   ├── PKGBUILD.work
│   │   │   ├── build-addon.sh
│   │   │   ├── pkg/
│   │   │   └── src/
│   │   ├── dbus/                  # D-Bus policy and service files
│   │   └── proton-vpn-manager.spec  # RPM spec file
│   ├── pytest.ini                  # pytest configuration
│   ├── Makefile                    # Build tasks
│   ├── README.md                   # Project overview
│   ├── TESTING.md                  # Testing guide
│   ├── MASTER_README.md
│   ├── MULTIUSER_SYSTEM.md
│   ├── TODO-*.md                   # Feature tracking by component
│   ├── IMPLEMENTATION_REPORT.md
│   ├── PROGRESS_SUMMARY.md
│   ├── ADAPTER_COMPLETION_SUMMARY.md
│   ├── COMPLETE_INTEGRATION_SUMMARY.md
│   ├── INTEGRATION_COMPLETE.md
│   ├── ARCH_LINUX_SUMMARY.md
│   ├── ALL_CHANGES_SUMMARY.md
│   └── .venv/                      # Local virtualenv (gitignored)
├── .build-venv/                    # Build-time virtualenv (PyInstaller hooks)
├── packaging/                      # Top-level packaging (legacy?)
│   ├── arch/
│   └── proton-vpn-cli-*.pkg.tar.zst  # Built Arch packages
├── multi-tunnel-policy-routing/    # Related project? (policy routing)
├── protonvpn.spec                 # Another spec file?
├── build-all-binaries.sh          # Binary build orchestration
├── build-binaries.sh              # Binary build script
├── check-deps.sh                  # Dependency checker
├── CONV.txt                       # Conversion notes?
├── QUICKSTART_BINARY.md
├── QUICK_REFERENCE.md
├── verify-packages.sh
├── .gitignore
├── .gitlab-ci.yml
├── CONTRIBUTING.md
├── COPYING.md
└── CODEOWNERS
```

## Key Directories

### `multi-tunnel-namespace/src/`

Primary source tree using **src layout pattern** (packages under `src/` prevents accidental imports from working directory).

#### `src/adapters/`
Standalone adapter executables. Each adapter is a separate Python package with its own `pyproject.toml`, allowing independent dependency management.

#### `src/libvpnmanager/`
Core library shared by daemon and adapters. This is the main API surface.

**Important modules:**
- `manager.py: TunnelManager` - High-level orchestrator, can be used directly (without daemon)
- `client.py: Client` - Connects to running daemon via IPC
- `adapters/base.py: VPNAdapter` - Base class for adapter implementations
- `routing/namespace.py: NetworkNamespaceRouting` - Linux network namespace ops
- `sessions/manager.py: SessionManager` - Multi-user session tracking

#### `src/daemon/`
MTM daemon implementation.

- `daemon.py: VPNDaemon` - Main daemon class, spawns adapters, handles IPC
- `adapter_registry.py: AdapterRegistry` - Discovers available adapters
- `resource_allocator.py: ResourceAllocator` - Network resource management

### `multi-tunnel-namespace/packaging/`

Build and distribution artifacts:
- **`arch/`** - Arch Linux packaging (PKGBUILD, build scripts)
- **`dbus/`** - D-Bus system policy and service files
- **`*.spec`** - RPM spec files for Fedora/RHEL

### `multi-tunnel-namespace/tests/`

Test suite organized as:
- `unit/` - Unit tests for individual components

Test framework: pytest with asyncio support, coverage configured in `pyproject.toml`.

### `multi-tunnel-namespace/docs/`

Architecture and design documentation.

## Naming Conventions

### Packages & Modules
- **libvpnmanager** - core library package (lowercase, underscores)
- **adapters** - subpackages per adapter: `proton_vpn_adapter`, `psiphon_adapter`, etc.
- **snake_case** for modules and packages

### Classes
- **PascalCase** for classes: `TunnelManager`, `VPNAdapter`, `NetworkNamespaceRouting`
- Abstract base classes end with base/strategy suffix

### Functions & Variables
- **snake_case** for functions and variables
- Async functions follow same convention: `async def create_tunnel(...)`

### Constants
- **UPPER_SNAKE_CASE** for module-level constants

### Entry Points
Console script names use hyphens: `proton-vpn-manager`, `mtm-adapter-proton`

## Entry Points Summary

| Entry Point | Module | Purpose |
|------------|--------|---------|
| `proton-vpn-manager` | `daemon.daemon:main` | Start MTM daemon |
| `mtm-adapter-proton` | `proton_vpn_adapter.cli:main` | Proton VPN adapter |
| `mtm-adapter-psiphon` | `psiphon_adapter.cli:main` | Psiphon adapter |
| `mtm-adapter-wireguard` | `wireguard_adapter.cli:main` | WireGuard adapter |
| `mtm-adapter-dummy` | `dummy_adapter.cli:main` | Dummy/test adapter |

## Configuration Locations

- **`pyproject.toml`** - Primary config: dependencies, tools (black, ruff, mypy, pytest)
- **`pytest.ini`** - Test discovery and options
- **`Makefile`** - Development tasks (test, lint, format, build)
- Adapter-specific `pyproject.toml` files for adapter-exclusive deps

---

*Generated by codebase mapper (arch focus)*
