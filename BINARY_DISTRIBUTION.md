# Standalone Binary Distribution Guide

This guide covers building and distributing Proton VPN CLI as standalone binaries that **do not require a Python interpreter** on the target system.

## Components

The project is split into **three main executables** when deployed as binaries:

| Binary | Description | Dependencies | Size (approx) |
|--------|-------------|--------------|---------------|
| `protonvpn` | Main CLI - all VPN commands, including tunnel management | systemd, dbus, wireguard | 80-120 MB |
| `proton-vpn-manager` | D-Bus daemon - handles multi-tunnel isolation, network namespaces, routing | systemd, dbus, pyroute2 | 80-120 MB |
| `libvpnmanager-*.whl` | Python library (optional) - for programmatic access to multi-tunnel API | Python (if used) | 200 KB |

All three are built using **PyInstaller** (executables) and **build** (wheel).

## Architecture

```
┌─────────────────┐
│   protonvpn     │   (standalone binary)
│   (CLI)         │
└────────┬────────┘
         │ D-Bus
         ▼
┌─────────────────┐
│ proton-vpn-     │   (standalone daemon binary)
│ manager         │
│ (libvpnmanager) │
└─────────────────┘

┌─────────────────┐
│ libvpnmanager   │   (wheel - optional)
│ (Python library)│
└─────────────────┘
```

- **protonvpn**: User-facing command-line tool. For simple VPN operations (connect, disconnect, list servers), it talks directly to the system agent. For tunnel commands (`protonvpn tunnel ...`), it communicates with `proton-vpn-manager` over D-Bus.

- **proton-vpn-manager**: System daemon that runs as root (via systemd). Manages network namespaces, routing, and TUN devices. Listens on D-Bus for CLI commands.

- **libvpnmanager**: Python library providing the core abstractions (TunnelManager, adapters, models). Both binaries embed this library internally, but it's also available as a wheel for developers.

## Prerequisites

### Build System Requirements

- **OS**: Linux (tested on Arch, should work on Fedora, Ubuntu 22.04+)
- **Python**: 3.9+
- **System packages**:
  ```bash
  # Arch
  sudo pacman -S base-devel python python-pip dbus systemd wireguard-tools

  # Ubuntu/Debian
  sudo apt-get install build-essential python3 python3-pip dbus systemd wireguard-tools
  ```

- **Virtual environment** with:
  - Project dependencies: `pip install -e .`
  - Build tools: `pip install pyinstaller build`
  - Internal Proton packages accessible (see below)

### Internal Proton Packages

The project depends on internal Proton packages **not available on PyPI**:

- `proton-core`
- `proton-vpn-api-core`
- `proton-keyring-linux`
- `proton-vpn-local-agent`

You must configure access to Proton's internal PyPI registry:

```bash
# Obtain a GitLab personal access token with 'api' scope
# Then configure pip:
pip config set global.index-url https://__token__<YOUR_TOKEN>@gitlab.example.com/api/v4/groups/<GROUP_ID>/-/packages/pypi/simple
```

See [README.md](README.md#virtual-environment) for details.

## Building

```bash
# 1. Create virtual environment
python -m venv .build-venv
source .build-venv/bin/activate

# 2. Install project dependencies
pip install --upgrade pip
pip install -e .  # Installs proton-vpn-cli and its dependencies

# 3. Install build tools
pip install pyinstaller build

# 4. Build all binaries
./build-all-binaries.sh
```

**Output**:

- `dist/protonvpn` - Main CLI binary
- `dist/proton-vpn-manager` - Daemon binary
- `multi-tunnel-namespace/dist/libvpnmanager-*.whl` - Library wheel

Build time: 5-15 minutes depending on hardware.

## Installing on Target System

### 1. Install Binaries

```bash
# Copy executables to a directory in PATH
sudo cp dist/protonvpn /usr/local/bin/
sudo cp dist/proton-vpn-manager /usr/local/bin/

# Make executable (should already be)
sudo chmod 755 /usr/local/bin/protonvpn /usr/local/bin/proton-vpn-manager
```

### 2. Install System Dependencies

The binaries require **shared libraries** to be present on the system:

```bash
# Arch
sudo pacman -S dbus systemd wireguard-tools

# Ubuntu/Debian
sudo apt-get install dbus systemd wireguard-tools
```

### 3. Enable and Start Daemon (for tunnel features)

The `proton-vpn-manager` daemon must be running for tunnel commands:

```bash
# Create systemd service file (provided separately or from packaging/)
sudo cp service/proton-vpn-manager.service /etc/systemd/system/
sudo systemctl daemon-reload
sudo systemctl enable --now proton-vpn-manager.service

# Check status
systemctl status proton-vpn-manager
```

### 4. Install libvpnmanager Wheel (Optional)

If you want to use `libvpnmanager` from Python scripts directly:

```bash
pip install multi-tunnel-namespace/dist/libvpnmanager-*.whl
```

**Note**: This is optional because both `protonvpn` and `proton-vpn-manager` already **embed** libvpnmanager internally. You only need the wheel if writing custom Python code that uses libvpnmanager.

### 5. Polkit Rules (for non-root operation)

The daemon needs to run as root, but CLI should be usable by regular users. Install Polkit rules to authorize users:

```bash
# Copy rules (if available in packaging/)
sudo cp multi-tunnel-namespace/packaging/arch/50-proton-vpn-manager.pkla /etc/polkit-1/rules.d/
# Or: sudo cp service/proton-vpn-manager.policy /usr/share/polkit-1/actions/
```

Without Polkit rules, you may need to run `protonvpn` with `sudo` for tunnel commands.

## Testing Installation

```bash
# Test main CLI
protonvpn --version
protonvpn --help
protonvpn servers list  # Should work with your Proton account

# Test tunnel commands (requires daemon running)
protonvpn tunnel list
protonvpn tunnel create mytunnel --adapter proton --session work --country US

# Test daemon directly
proton-vpn-manager --help  # May show usage
# Check daemon logs
journalctl -u proton-vpn-manager -f
```

## Binary Internals

### What's Inside the Binaries?

Each standalone binary contains:

- **Embedded Python interpreter** (libpython3.14.so.1.0)
- **Compiled bytecode** for all Python modules
- **Pure Python dependencies** (click, tabulate, dbus-fast, proton packages, libvpnmanager, etc.)
- **Data files** (package data, configuration templates if any)
- **No dynamic loading** of external Python packages (except system C libraries)

### What's NOT Included?

- **System libraries**: `libdbus-1.so`, `libsystemd.so`, `libwireguard.so`, `libc.so`. These must be provided by the OS.
- **Kernel modules**: `wireguard` kernel module (usually built-in on modern kernels)
- **C extensions for pyroute2**: If pyroute2 uses C加速, those compiled `.so` files are included if present in the build environment. Some features may fall back to pure Python.

### Binary Size Breakdown (approx)

| Component | Size |
|-----------|------|
| Python interpreter | 40 MB |
| Standard library (selected) | 20 MB |
| Application code + dependencies | 30-60 MB |
| **Total per binary** | **80-120 MB** |

## Troubleshooting

### Missing shared library

```
error while loading shared libraries: libdbus-1.so.3: cannot open shared object file
```

**Fix**: Install the missing library:
```bash
# libdbus-1.so
sudo pacman -S dbus    # Arch
sudo apt-get install libdbus-1-3  # Ubuntu/Debian
```

### Daemon fails to start

```
Failed to start proton-vpn-manager.service: Unit proton-vpn-manager.service not found.
```

**Fix**: Create and enable the systemd service (see Step 3 above).

### Tunnel commands say "libvpnmanager not available"

This should not happen if you're using the `protonvpn` binary built with embedded libvpnmanager. If you're using a version without libvpnmanager embedded, install the wheel:

```bash
pip install libvpnmanager-*.whl
```

Or rebuild `protonvpn` with libvpnmanager included (default in our build script).

### Permission denied on D-Bus

When running `protonvpn tunnel ...`, you may see D-Bus permission errors. This means Polkit rules are not set up. Either:

- Install the Polkit rules, or
- Run with `sudo` (not recommended for daily use), or
- Add your user to the appropriate group (e.g., `wheel` or a dedicated `vpn` group).

### Binary fails to start with "cannot find module X"

If PyInstaller missed a hidden import, the binary will crash with `ModuleNotFoundError`. To fix, rebuild with additional `--hidden-import` flags in the spec file.

Example: If you see `No module named 'xyz'`, add `'xyz'` to the `hiddenimports` list in the spec and rebuild.

### Binary is too large

We already exclude many unnecessary modules (`tkinter`, `numpy`, etc.). If you need to reduce size further:

- Edit the spec file's `excludes` list to remove more modules.
- Disable UPX compression if it's not effective.
- Use `--onedir` instead of `--onefile` (but this creates a directory, not a single file).

### Debugging build issues

PyInstaller creates `build/<exename>/warn-<exename>.txt` with missing module warnings. Check that file.

Also inspect the analysis:

```bash
# List bundled modules
pyi-archive_viewer dist/protonvpn | less
```

## Advanced: Customizing Builds

### Changing Optimization Level

In the spec file, add `optimize=2` to the `EXE` call to enable Python bytecode optimization (removes asserts, docstrings). Slightly smaller, faster, but harder to debug.

### Stripping Debug Symbols

After build, strip the binary to reduce size:

```bash
strip dist/protonvpn dist/proton-vpn-manager
```

Note: Stripping makes crashes harder to debug. Keep an unstripped version for development.

### Building for Different Architectures

By default, PyInstaller builds for the current architecture. For cross-compilation, you need a cross-compilation toolchain and appropriate Python interpreter for the target.

### Partial Builds (Debugging)

If you want to inspect the extracted files, build in `--onedir` mode:

```bash
pyinstaller --onedir protonvpn-cli.spec
```

This creates `dist/protonvpn/` with the executable and all dependent files. Useful for debugging path issues.

## Distribution Packages

### Arch Linux PKGBUILD

See `packaging/arch/` for PKGBUILD files that create native Arch packages (`proton-vpn-cli`, `proton-vpn-manager`). These can use the pre-built binaries or build from source.

### Generic Linux Binary Tarball

Create a tarball for distribution:

```bash
mkdir -p package/usr/local/bin
cp dist/protonvpn dist/proton-vpn-manager package/usr/local/bin/
tar czf proton-vpn-cli-binaries.tar.gz -C package .
```

Include a README with installation instructions and required system dependencies.

## Comparing to Traditional pip Install

| Aspect | Binary Distribution | pip install |
|--------|-------------------|-------------|
| **Requirements** | Only system libs (dbus, systemd) | Full Python 3.9+ + pip |
| **Installation** | Copy binary to PATH | `pip install proton-vpn-cli` |
| **Updates** | Replace binary | `pip install --upgrade` |
| **Size** | 80-120 MB per binary | Small (few KB) + shared Python |
| **Startup** | Slightly slower (extraction cache) | Fast |
| **Portability** | Works on systems without Python | Requires compatible Python |
| **Debugging** | Hard (obfuscated bytecode) | Easy (source available) |
| **Dependency conflicts** | None (isolated) | Possible (shared environment) |

## Security Considerations

- Binaries are **not signed** by default. Consider code signing with `signtool` or `gpg` for distribution.
- The embedded Python includes the full standard library; this may increase attack surface. However, the binary runs with user privileges only (except daemon runs as root via systemd).
- Verify binary integrity with SHA256 checksums when downloading.

## Uninstallation

```bash
# Remove binaries
sudo rm /usr/local/bin/protonvpn /usr/local/bin/proton-vpn-manager

# Remove daemon service
sudo systemctl disable --now proton-vpn-manager
sudo rm /etc/systemd/system/proton-vpn-manager.service

# Remove libvpnmanager wheel (if installed)
pip uninstall libvpnmanager
```

## Support

- Build issues: Check `BINARY_BUILD.md` for detailed build instructions.
- Usage help: `protonvpn --help` or https://protonvpn.com/support-form
- Bug reports: https://github.com/ProtonVPN/proton-vpn-cli/issues
