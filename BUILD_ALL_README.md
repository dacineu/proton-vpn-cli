# Building All Standalone Binaries

Quick guide to build the complete set of standalone executables for Proton VPN CLI.

## Files in This Repository

| File | Purpose |
|------|---------|
| `build-all-binaries.sh` | Main build script - creates all 3 artifacts |
| `check-deps.sh` | Checks system dependencies (dbus, systemd, wireguard) |
| `BINARY_DISTRIBUTION.md` | Comprehensive distribution guide |
| `BINARY_BUILD.md` | Detailed build documentation |
| `QUICKSTART_BINARY.md` | Quick reference for end users |
| `Makefile.binaries` | Alternative make-based build interface |

## Quick Start

```bash
# 1. Check system dependencies
./check-deps.sh

# 2. Setup virtual environment (if not done)
python -m venv .build-venv
source .build-venv/bin/activate
pip install --upgrade pip

# 3. Configure internal PyPI (one-time)
#    Get token from https://gitlab.example.com/profile/personal_access_tokens
pip config set global.index-url https://__token__<TOKEN>@gitlab.example.com/api/v4/groups/<GROUP>/-/packages/pypi/simple

# 4. Install project dependencies
pip install -e .

# 5. Install build tools
pip install pyinstaller build

# 6. Build everything
./build-all-binaries.sh
```

After ~10 minutes, you'll have:

- `dist/protonvpn` - Main CLI (80-120 MB)
- `dist/proton-vpn-manager` - Daemon (80-120 MB)
- `multi-tunnel-namespace/dist/libvpnmanager-*.whl` - Library (200 KB)

## Install

```bash
sudo cp dist/protonvpn /usr/local/bin/
sudo cp dist/proton-vpn-manager /usr/local/bin/
sudo systemctl enable --now proton-vpn-manager   # for tunnel features
```

## Troubleshooting

### "No module named 'proton_core'"

The internal Proton packages are not installed. Ensure you have:

1. Valid access token for Proton's internal PyPI
2. Correct `pip config` index URL set
3. Network connectivity to GitLab

Test with:
```bash
pip list | grep proton
```

You should see: proton-core, proton-vpn-api-core, proton-keyring-linux, proton-vpn-local-agent.

If missing, re-run `pip install -e .` after configuring pip.

### Build fails with "module not found" warnings

PyInstaller may miss some hidden imports. Check `build/*/warn-*.txt` for missing modules. You may need to manually add them to the `hiddenimports` list in the `.spec` file.

Common additions:
- `'pyroute2.netlink.rtnl.rtmsg'`
- `'pyroute2.netlink.rtnl.ifinfmsg'`
- `'systemd.daemon'`

### Binary is much larger than expected

This is normal. The binaries include the entire Python interpreter (~40 MB) and all dependencies.

If >200 MB, check for unnecessary inclusions. You can add more modules to the `excludes` list in the spec.

### Binary runs but D-Bus calls fail

Ensure `dbus-daemon` is running:
```bash
systemctl --user status dbus
# or start it:
systemctl --user start dbus
```

Most desktop environments start D-Bus automatically. On headless servers, you may need to start it manually.

### Daemon fails to start with "permission denied"

The daemon needs to open TUN devices and manipulate network namespaces. Ensure it runs as root (systemd service runs as root by default). Also check:

- `sudo sysctl -w net.ipv4.ip_forward=1`
- `sudo sysctl -w net.ipv6.conf.all.forwarding=1`

### "Cannot open shared object file" for libdbus, libsystemd

Install system libraries:

- Arch: `sudo pacman -S dbus systemd`
- Ubuntu: `sudo apt-get install libdbus-1-3 libsystemd0`

## Advanced Build Options

### Build without onefile (for debugging)

Edit the spec file: change `a = Analysis(...)` to add `--onedir` when running pyinstaller, or modify the spec to not use `COLLECT` with single EXE. Easier: just run:

```bash
pyinstaller --onedir protonvpn-cli.spec
```

This creates a directory with the executable plus shared libraries, easier to inspect.

### Reduce binary size

In the spec file, add more exclusions:

```python
excludes=[
    'tkinter', 'matplotlib', 'numpy', 'scipy', 'pandas',
    'PIL', 'PyQt5', 'PySide2', 'wx', 'test', 'unittest',
    'pytest', 'quart', 'flask', 'django', 'sqlalchemy',
    'email', 'html', 'http', 'xml', 'urllib', 'logging.handlers',
]
```

### Change optimization level

Add `optimize=2` to `EXE()` call:

```python
exe = EXE(
    ...
    optimize=2,
    ...
)
```

This removes docstrings and assert statements. Smaller but debugging harder.

### Build for older Linux distributions

If targeting older glibc (e.g., CentOS 7), build on an older system (or use Docker with older base image). PyInstaller bundles Python shared library which is tied to glibc version.

## What Each Binary Contains

### protonvpn

- Main CLI entry point: `proton.vpn.cli:main`
- All commands: account, servers, connect, disconnect, settings, **tunnel**
- Embedded libvpnmanager (for tunnel commands)
- Embedded Proton core packages
- Embedded Python 3.14

**Purpose**: End-user CLI for all operations.

### proton-vpn-manager

- Daemon entry point: `daemon.daemon:main`
- Full libvpnmanager library (manager, routing, sessions, adapters)
- D-Bus service implementation
- Embedded Python 3.14

**Purpose**: System daemon that performs privileged operations (network namespace creation, routing). Must run as root.

### libvpnmanager wheel

- Pure Python library (libvpnmanager package)
- No embedded interpreter
- Can be pip-installed

**Purpose**: For developers who want to use libvpnmanager directly in their Python code, or for systems where you want to share the library across multiple applications.

## Installation Layout

After installation on target system:

```
/usr/local/bin/
├── protonvpn            (executable)
└── proton-vpn-manager   (executable)

/usr/lib/python3.14/site-packages/   (if libvpnmanager wheel installed)
└── libvpnmanager/

/etc/systemd/system/
└── proton-vpn-manager.service

/etc/polkit-1/rules.d/
└── 50-proton-vpn-manager.pkla

/var/log/
└── proton-vpn-manager.log  (journald)
```

## Uninstalling

```bash
# Remove binaries
sudo rm /usr/local/bin/protonvpn /usr/local/bin/proton-vpn-manager

# Disable and remove daemon
sudo systemctl disable --now proton-vpn-manager
sudo rm /etc/systemd/system/proton-vpn-manager.service
sudo systemctl daemon-reload

# Remove library wheel (if installed)
pip uninstall libvpnmanager
```

## Support

For issues:
- Build problems: Check `BINARY_BUILD.md` and this file
- Runtime problems: `BINARY_DISTRIBUTION.md`
- General: https://protonvpn.com/support-form

## Next Steps

- Create systemd service file for `proton-vpn-manager`
- Create Polkit rules for non-root tunnel commands
- Package into .deb/.rpm using the provided packaging/ scripts
- Test on clean systems (no Python installed)
