# Architecture Restructure TODO

This document tracks the tasks for restructuring the multi-tunnel VPN project.

## Completed Tasks

✅ **Task 1: Create Core libvpnmanager Package**
- Moved TunnelManager, routing, sessions (base only), models, dbus, adapters (base only) to `src/libvpnmanager/`
- Created proper package structure with `__init__.py` files
- Fixed relative imports throughout
- TunnelManager is in `src/libvpnmanager/manager.py` (no separate `manager/` subpackage)

✅ **Task 2: Split Adapters into Separate Packages**
- Created adapter packages:
  - `proton_vpn_adapter/`
  - `psiphon_adapter/`
  - `wireguard_adapter/`
  - `dummy_adapter/`
- Each contains:
  - `adapter.py` (implementation of `VPNAdapter`)
  - `sessions/` with concrete Session classes
  - `pyproject.toml`
  - `__init__.py`
- Copied and fixed imports to use `libvpnmanager` core

✅ **Task 3: Update Daemon for Plugin Adapters**
- Modified `daemon/daemon.py` to:
  - Dynamically import available adapters (try/except)
  - Call `manager.register_adapter_type()` for each available adapter
  - Support `enabled_adapters` configuration
  - Log available adapters on startup

✅ **Task 4: Package Metadata for Adapters**
- Created `pyproject.toml` for each adapter package
- Declared dependencies (e.g., `proton_vpn_adapter` depends on `libvpnmanager` and proton internal packages)
- Added optional dev dependencies

✅ **Task 5: Standardize Adapter Interface**
- All adapters accept `session` (a Session instance) in `__init__`
- Session classes implement `create()` class method
- SessionManager uses registry pattern for session types
- Removed hardcoded session type mappings

✅ **Task 6: Create Core Subpackage __init__ Files**
- routing/__init__.py
- sessions/__init__.py
- models/__init__.py
- dbus/__init__.py
- (Note: `adapters/` is a namespace package; no __init__.py)
- (No separate manager/ package; manager.py sits directly in libvpnmanager)

## Remaining Tasks

✅ **Task 7: Update Build System**
- Updated Arch PKGBUILD's PyInstaller spec to use `adapters.` prefixed imports
- Updated `build-all-binaries.sh` daemon spec with correct import paths and datas
- Created/updated `proton-vpn-manager.spec` with corrected module paths
- Spec files now include:
  - `adapters.dummy_adapter`, `adapters.proton_vpn_adapter`, `adapters.psiphon_adapter`, `adapters.wireguard_adapter`
  - `libvpnmanager.sessions.dummy`
  - `libvpnmanager.adapters.dummy` (core's dummy)
- Removed references to top-level adapter packages (now under `adapters/`)

Note: build-binaries.sh relies on the external proton-vpn-manager.spec; that spec is updated.

⏳ **Task 8: Verify Build and Runtime** (in progress)
- Syntax check: all modules compile successfully ✅
- Daemon import test: succeeds after adapter import fixes ✅
- Adapter signatures standardized ✅
- Integration example updated to use new registration pattern ✅
- Next: Run full build with PyInstaller in a proper venv to verify binary creation
- Run unit tests to ensure no regressions
- Test daemon startup and adapter discovery with DummyAdapter

✅ **Task 9: Create CLI Packages** (mostly done)
- Tunnel commands implemented in `src/cli/tunnel.py`
- Commands use `VPNManagerClient` (D-Bus) and are ready for integration
- `protonvpn` CLI build script includes libvpnmanager (client + models)
- Separate CLI packages for Psiphon/WireGuard are optional; can be built similarly
- Note: Integration into main protonvpn CLI (command registration) remains

✅ **Task 10: Update Documentation**
- Created comprehensive architecture documents:
  - `docs/REASONING.md` (design reasoning)
  - `docs/RESTRUCTURE_SUMMARY.md` (previous summary)
  - `docs/ARCHITECTURE_RESTRUCTURE.md` (detailed changes)
  - `docs/ARCHITECTURE_UML.md` (sequence/component diagrams)
  - `docs/RESTRUCTURE_COMPLETE_SUMMARY.md` (final summary)
  - `docs/RESTRUCTURE_TODO.md` (this file)
- Updated `IMPLEMENTATION_REPORT.md` with current status
- `MULTI_TUNNEL_ARCHITECTURE.md` and `MULTI_TUNNEL_INDEX.md` provide overviews
- TODO: update top-level README.md with new structure and build instructions

## Notes

- The monorepo remains: all packages live under `multi-tunnel-namespace/`
- Build process produces:
  - `proton-vpn-manager` binary (includes core + all adapters)
  - `libvpnmanager` wheel (pure Python library)
  - `protonvpn` CLI binary (includes D-Bus client)
- The architecture follows clean separation:
  - **Core**: infrastructure, no service-specific code
  - **Adapters**: one per VPN service, depend on core and service libraries
  - **CLI**: user interfaces, D-Bus clients
- Adapter packages are located under `src/adapters/` as a namespace package.

## Notes

- The monorepo remains: all packages live under `multi-tunnel-namespace/`
- Build process will produce:
  - `proton-vpn-manager` binary (includes core + all adapters)
  - Individual adapter wheels (optional)
  - CLI binaries (standalone or system packages)
- The architecture follows clean separation:
  - **Core**: infrastructure, no service-specific code
  - **Adapters**: one per VPN service, depend on core and service libraries
  - **CLI**: user interfaces, D-Bus clients
