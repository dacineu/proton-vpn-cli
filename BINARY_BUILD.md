# Standalone Binary Build

This document describes how to build and deploy Proton VPN CLI as a standalone binary that does not require a separate Python interpreter.

## Overview

The build process creates two artifacts:

1. **protonvpn** - A single-file executable containing:
   - Embedded Python 3.14 interpreter
   - All pure Python dependencies (click, tabulate, dbus-fast, etc.)
   - Proton VPN CLI codebase
   - **Does NOT include libvpnmanager** (provided separately)

2. **libvpnmanager** - A wheel (`.whl`) binary package containing:
   - The libvpnmanager Python library
   - Can be installed via `pip install libvpnmanager-*.whl`

## Prerequisites

### System Dependencies

The target system must have:

- **Linux** (this build is Linux-specific due to dbus and network namespace usage)
- System libraries:
  - `libdbus-1.so` (dbus)
  - `libsystemd.so` (systemd)
  - `libwireguard.so` (wireguard-tools)
  - Standard C library (glibc)
- Kernel support for network namespaces and WireGuard

On Arch Linux:
```bash
sudo pacman -S dbus systemd wireguard-tools
```

### Python Dependencies

You need a Python environment with:

1. **Proton internal packages** (not available on PyPI):
   - `proton-core`
   - `proton-vpn-api-core`
   - `proton-keyring-linux`
   - `proton-vpn-local-agent`

   These must be installed from your internal PyPI registry. See [README.md](README.md#virtual-environment) for setup.

2. **Build tools**:
   ```bash
   pip install pyinstaller build
   ```

## Building

1. Create and activate a virtual environment:
   ```bash
   python -m venv .build-venv
   source .build-venv/bin/activate
   ```

2. Install all dependencies:
   ```bash
   # Configure internal PyPI registry first (see README.md)
   pip install -e .
   pip install pyinstaller build
   ```

3. Run the build script:
   ```bash
   ./build-binaries.sh
   ```

## Outputs

After successful build:

- `dist/protonvpn` - Standalone executable (~50-80 MB)
- `multi-tunnel-namespace/dist/libvpnmanager-*.whl` - libvpnmanager wheel

## Installation on Target System

### Step 1: Install libvpnmanager (Optional - for tunnel commands)

```bash
# Copy the wheel to the target system and install:
pip install libvpnmanager-0.1.0.dev0-py3-none-any.whl
```

This installs the libvpnmanager library and its Python dependencies (`dbus-next`, `pydantic`, `asyncstdlib`, `pyroute2`, `systemd-python`).

**Note:** libvpnmanager requires the `protonvpn.service` daemon to be running. Install the `proton-vpn-manager` package to get the daemon.

### Step 2: Install Proton Core Dependencies

```bash
pip install proton-core proton-vpn-api-core proton-keyring-linux proton-vpn-local-agent
```

These are required for basic VPN functionality (connect, disconnect, servers, etc.).

### Step 3: Install the protonvpn Binary

```bash
# System-wide:
sudo cp dist/protonvpn /usr/local/bin/

# Or for user only:
mkdir -p ~/.local/bin
cp dist/protonvpn ~/.local/bin/
```

Make sure `~/.local/bin` is in your `$PATH`.

## Usage

```bash
# Check version
protonvpn --version

# Get help
protonvpn --help

# Basic commands (work without libvpnmanager)
protonvpn servers list
protonvpn connect --country US
protonvpn disconnect

# Tunnel commands (only work if libvpnmanager installed)
protonvpn tunnel list
protonvpn tunnel create mytunnel --adapter proton --session work --country DE
```

## How It Works

### PyInstaller Analysis

PyInstaller performs static analysis on `proton/vpn/cli/__init__.py` and:

1. Collects all imported Python modules
2. Bundles them with the Python interpreter into a single executable
3. Extracts data files (command modules, etc.) to a temporary directory at runtime
4. Creates a self-extracting archive that runs the embedded Python code

### libvpnmanager Separation

libvpnmanager is excluded from the protonvpn binary because:

- It's an optional component (multi-tunnel feature)
- It has heavy dependencies (pyroute2, systemd-python) that may already be system-managed
- It allows independent updates and versioning
- The daemon component (`protonvpn.service`) is managed separately via systemd

The `tunnel` command group checks for libvpnmanager at runtime:
```python
try:
    from libvpnmanager.dbus.client import VPNManagerClient
    HAS_LIBVPNMANAGER = True
except ImportError:
    HAS_LIBVPNMANAGER = False
```

## Troubleshooting

### Missing Module Errors

If you get `ModuleNotFoundError`, the binary may have missed some hidden import. Rebuild with additional `--hidden-import` flags.

### libdbus Not Found

Ensure `libdbus-1.so` is installed:
```bash
ldconfig -p | grep libdbus-1
```

If missing: `sudo pacman -S dbus`

### Daemon Not Running

For libvpnmanager operations, the daemon must be active:
```bash
systemctl status protonvpn.service
sudo systemctl start protonvpn.service
sudo systemctl enable protonvpn.service
```

### Binary Too Large

The binary includes the full Python interpreter (~40 MB). Use `--exclude-module` to reduce size, but be careful not to exclude needed modules.

### Debugging Build Issues

Check the PyInstaller analysis:
```bash
pyinstaller --onedir protonvpn-cli.spec  # Build without onefile for easier debugging
```

Check what's included:
```bash
pyi-archive_viewer dist/protonvpn  # If using onefile
# or
ls dist/protonvpn/  # If using onedir
```

## Advanced: Customizing the Build

Edit `protonvpn-cli.spec` to:

- Add additional data files: `datas=[('path/to/file', 'destination/in/bundle')]`
- Exclude more modules: `excludes=['module1', 'module2']`
- Change optimization level: `optimize=2` (default is 0)
- Enable UPX compression: `upx=True` (requires `upx` installed)
- Change the executable name: `name='newname'`

After modifying the spec file, rebuild:
```bash
pyinstaller protonvpn-cli.spec
```

## Distribution

### Arch Linux Package

The `packaging/arch/` directory contains PKGBUILD files for creating Arch packages:

- `proton-vpn-cli` - The CLI (can use the standalone binary)
- `proton-vpn-manager` - The libvpnmanager daemon

See `ARCH_PACKAGES_README.md` for details.

### Generic Linux Binary

The `dist/protonvpn` binary should work on most modern Linux distributions with glibc 2.35+ (Arch, Fedora 38+, Ubuntu 22.04+).

To distribute:
1. Provide the binary
2. Document required system packages (dbus, systemd, wireguard-tools)
3. Provide instructions for installing libvpnmanager if multi-tunnel features are needed

## Security Considerations

- The binary includes the full Python standard library. Consider stripping debug symbols for production:
  ```bash
  strip dist/protonvpn
  ```

- Verify the binary hasn't been tampered with using checksums/SIGNATURES if distributing over networks.

- The binary runs with the user's privileges. All privileged operations go through the systemd daemon via D-Bus.

## Performance

Startup time is slower than a pure Python script because PyInstaller extracts files to a temporary directory (~50-100 MB) on first run. Subsequent runs are faster due to OS caching.

Typical sizes:
- Protonvpn standalone binary: 50-80 MB
- libvpnmanager wheel: 100-200 KB (pure Python)

## Comparison: Binary vs. Traditional Python Package

| Aspect | Binary | Traditional (pip install) |
|--------|--------|---------------------------|
| Dependencies | Embedded Python, external system libs | Python 3.9+ + pip packages |
| Installation | Copy binary to PATH | `pip install proton-vpn-cli` |
| Size | Large (50-80 MB) | Small (few KB) + shared Python |
| Startup | Slower (extraction overhead) | Faster (direct import) |
| Updates | Replace binary | `pip install --upgrade` |
| Portability | Works on target Linux without Python | Requires matching Python version |
| Debugging | Harder (obfuscated) | Easier (source available) |

Choose the binary approach for:
- Systems without Python or with version conflicts
- Simplified deployment (single file)
- Distribution to end-users

Choose traditional pip install for:
- Development environments
- Systems with stable Python environments
- Easier debugging and modification
