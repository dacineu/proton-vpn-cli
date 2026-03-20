# Quick Start: Binary Proton VPN CLI

## Prerequisites Check

Before building, ensure you have:

```bash
# System dependencies (Arch Linux)
sudo pacman -S dbus systemd wireguard-tools base-devel python python-pip

# Internal Proton packages MUST be accessible via pip
# See: https://protonvpn.com/docs or contact Proton IT for the internal PyPI URL
```

## Build Steps

```bash
# 1. Setup build environment
python -m venv .build-venv
source .build-venv/bin/activate
pip install --upgrade pip

# 2. Configure internal PyPI (one-time)
pip config set global.index-url https://__token__<YOUR_TOKEN>@gitlab.example.com/api/v4/groups/<GROUP>/-/packages/pypi/simple

# 3. Install dependencies
pip install -e .

# 4. Install build tools
pip install pyinstaller build

# 5. Build binaries
./build-binaries.sh
```

## Output Files

- `dist/protonvpn` - Standalone CLI binary (~70 MB)
- `multi-tunnel-namespace/dist/libvpnmanager-*.whl` - Multi-tunnel library (~200 KB)

## Install on System

```bash
# Option A: Install manually
sudo cp dist/protonvpn /usr/local/bin/
pip install multi-tunnel-namespace/dist/libvpnmanager-*.whl  # for tunnel features
sudo systemctl enable --now protonvpn.service  # if using multi-tunnel

# Option B: Create local packages (Arch Linux)
# See packaging/arch/ARCH_LINUX_SUMMARY.md
```

## Verify Installation

```bash
protonvpn --version
protonvpn --help
protonvpn servers list
protonvpn tunnel list  # Only works if libvpnmanager installed
```

## Troubleshooting

| Issue | Solution |
|-------|----------|
| `Error: libdbus-1.so not found` | `sudo pacman -S dbus` |
| `protonvpn: command not found` | Add `~/.local/bin` to PATH or use `/usr/local/bin/protonvpn` |
| `ModuleNotFoundError: proton.core` | Install proton-core from internal PyPI |
| Tunnel commands fail with "libvpnmanager not available" | Install libvpnmanager wheel |
| Binary fails to start | Check `/tmp/_MEI*` permissions, ensure enough disk space for extraction |

## What's Inside the Binary

```
protonvpn (ELF executable)
├── Embedded Python 3.14 interpreter
├── Standard library (select modules)
├── Third-party packages:
│   ├── click
│   ├── tabulate
│   ├── dbus-fast
│   └── proton-* packages (if installed during build)
└── Proton VPN CLI code:
    ├── commands/ (account, server, settings, etc.)
    └── core/ (controller, exception handling)
```

**NOT included** (must be installed separately):
- `libvpnmanager` (multi-tunnel features)
- Native system libraries (libdbus-1.so, libsystemd.so, libwireguard.so)

## Binary Size Optimization

To reduce binary size, edit `protonvpn-cli.spec`:

```python
excludes=[
    'tkinter',
    'numpy',
    'scipy',
    'PIL',
    'test',
    'unittest',
    # Add more as needed
]
```

Then rebuild:
```bash
pyinstaller protonvpn-cli.spec
```

## Distribution

The built binary works on:
- Arch Linux (tested)
- Fedora 38+
- Ubuntu 22.04+
- Any Linux with glibc 2.35+

For older systems, you may need to build on an older distribution or use `auditwheel`/`delvewheel` to ensure compatibility.

## Need Help?

- Full build docs: [BINARY_BUILD.md](BINARY_BUILD.md)
- Project README: [README.md](README.md)
- Report issues: https://protonvpn.com/support-form
