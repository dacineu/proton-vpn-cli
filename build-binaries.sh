#!/usr/bin/env bash
#
# Build standalone binaries for proton-vpn-cli and proton-vpn-manager
#
# This creates:
#   1. A standalone protonvpn binary (without libvpnmanager)
#   2. A proton-vpn-manager daemon binary (includes libvpnmanager)
#   3. A libvpnmanager wheel that can be installed separately
#
# Prerequisites:
# - Python 3.9+
# - Virtual environment with ALL dependencies installed:
#   pip install -e .  # Installs proton-vpn-cli and its dependencies
#   pip install pyinstaller build
#
# Usage:
#   source .build-venv/bin/activate
#   ./build-binaries.sh
#
# Note: Internal Proton packages must be accessible via pip configuration
#       (see README.md for setting up the internal PyPI registry)

set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$SCRIPT_DIR"

echo "=== Building proton-vpn-cli standalone binary (without libvpnmanager) ==="
echo ""

# Clean previous builds
rm -rf dist/ build/ *.spec
mkdir -p dist

# Build the main CLI with PyInstaller
cd "$SCRIPT_DIR"
source .build-venv/bin/activate

# Create a spec file for better control
cat > protonvpn-cli.spec << 'PYSPEC'
# -*- mode: python ; coding: utf-8 -*-

block_cipher = None

a = Analysis(
    ['proton/vpn/cli/__init__.py'],
    pathex=[],
    binaries=[],
    datas=[
        # Include command modules
        ('proton/vpn/cli/commands', 'proton/vpn/cli/commands'),
        ('proton/vpn/cli/core', 'proton/vpn/cli/core'),
    ],
    hiddenimports=[
        # CLI commands
        'proton.vpn.cli.commands.account',
        'proton.vpn.cli.commands.settings',
        'proton.vpn.cli.commands.servers',
        'proton.vpn.cli.commands.server',
        'proton.vpn.cli.commands.location_discovery',
        'proton.vpn.cli.commands.command_utils',
        # tunnel commands ARE included but will fail gracefully if libvpnmanager missing
        'proton.vpn.cli.commands.tunnel',
        # Core modules
        'proton.vpn.cli.core.controller',
        'proton.vpn.cli.core.exception_handler',
        'proton.vpn.cli.core.exceptions',
        'proton.vpn.cli.core.run_async',
        'proton.vpn.cli.core.wait_for_current_tasks',
        # Dependencies
        'click',
        'click.core',
        'click.decorators',
        'click.utils',
        'click.types',
        'click.exceptions',
        'dbus_fast',
        'dbus_fast.aio',
        'dbus_fast.message',
        'dbus_fast.signature',
        'dbus_fast.service',
        'dbus_fast.constants',
        'tabulate',
        'tabulate.table',
        'tabulate.plain',
        'asyncio',
        'importlib.metadata',
        # Proton dependencies (will be included if installed)
        'proton_core',
        'proton_core.api',
        'proton_core.api import *',
        'proton_vpn_api_core',
        'proton_vpn_api_core.api',
        'proton_vpn_api_core.api.client',
        'proton_vpn_api_core.api.exceptions',
        'proton_keyring_linux',
        'proton_keyring_linux.keyring',
        'proton_vpn_local_agent',
        'proton_vpn_local_agent.client',
    ],
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[
        # Exclude unnecessary large modules
        'tkinter',
        'matplotlib',
        'numpy',
        'scipy',
        'pandas',
        'PIL',
        'PyQt5',
        'PySide2',
        'wx',
        'test',
        'unittest',
        'pytest',
        'quart',
        'flask',
        'django',
        'sqlalchemy',
        # Exclude libvpnmanager - it will be provided as separate package
        'libvpnmanager',
        'libvpnmanager.*',
    ],
    win_no_prefer_redirects=False,
    win_private_assemblies=False,
    cipher=block_cipher,
    noarchive=False,
)

pyz = PYZ(a.pure, a.zipped_data, cipher=block_cipher)

exe = EXE(
    pyz,
    a.scripts,
    a.binaries,
    a.datas,
    [],
    name='protonvpn',
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    upx_exclude=[],
    runtime_tmpdir=None,
    console=True,
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
)
PYSPEC

# Build with PyInstaller
pyinstaller protonvpn-cli.spec

echo ""
echo "=== Building proton-vpn-manager daemon standalone binary ==="
echo ""

# Build the daemon from the multi-tunnel-namespace directory
# The daemon includes libvpnmanager and selected adapters
cd "$SCRIPT_DIR/multi-tunnel-namespace/src"
source "$SCRIPT_DIR/.build-venv/bin/activate"

# Clean previous daemon builds
rm -rf build/ dist/ *.spec

# Use the external spec file (already created and updated)
if [ ! -f "../proton-vpn-manager.spec" ]; then
    echo "ERROR: proton-vpn-manager.spec not found. Create it first."
    exit 1
fi

# Build with PyInstaller using the spec file
pyinstaller ../proton-vpn-manager.spec

# Move the binary to the main dist directory
if [ -f "dist/proton-vpn-manager" ]; then
    mv dist/proton-vpn-manager "$SCRIPT_DIR/dist/"
    # Cleanup build artifacts in src/
    rm -rf build/ dist/ *.spec
else
    echo "ERROR: Daemon binary not found after build"
    exit 1
fi

echo ""
echo "=== Building libvpnmanager as a wheel (binary package) ==="
cd "$SCRIPT_DIR/multi-tunnel-namespace"

# Clean and build libvpnmanager wheel
rm -rf dist/ build/ *.egg-info
source "$SCRIPT_DIR/.build-venv/bin/activate"
python -m build --wheel --no-isolation

echo ""
echo "=== Build Complete ==="
echo ""
echo "Outputs:"
echo "  1. protonvpn CLI binary:"
echo "     $SCRIPT_DIR/dist/protonvpn (or protonvpn.exe on Windows)"
echo ""
echo "  2. proton-vpn-manager daemon binary:"
echo "     $SCRIPT_DIR/dist/proton-vpn-manager"
echo ""
echo "  3. libvpnmanager wheel:"
echo "     $SCRIPT_DIR/multi-tunnel-namespace/dist/libvpnmanager-*.whl"
echo ""
echo "Installation:"
echo "  A. Install libvpnmanager separately (if not using daemon binary):"
echo "     pip install multi-tunnel-namespace/dist/libvpnmanager-*.whl"
echo ""
echo "  B. Install proton-* dependencies:"
echo "     # These are internal Proton packages - must be installed from your private PyPI"
echo "     pip install proton-core proton-vpn-api-core proton-keyring-linux proton-vpn-local-agent"
echo ""
echo "  C. Install the protonvpn binary:"
echo "     sudo cp $SCRIPT_DIR/dist/protonvpn /usr/local/bin/"
echo ""
echo "  D. Install the proton-vpn-manager daemon binary:"
echo "     sudo cp $SCRIPT_DIR/dist/proton-vpn-manager /usr/local/bin/"
echo "     # Or: sudo cp $SCRIPT_DIR/dist/proton-vpn-manager /usr/bin/"
echo ""
echo "  E. Enable and start the systemd service:"
echo "     sudo systemctl enable --now proton-vpn-manager.service"
echo ""
echo "Note: The protonvpn binary includes the Python interpreter and all pure Python"
echo "      dependencies. It does NOT include libvpnmanager, which must be installed"
echo "      separately as a wheel (unless using the daemon binary, which includes it)."
echo "      System libraries (libdbus-1.so, systemd, wireguard) must also be available"
echo "      on the target system."
echo ""
echo "Verify the builds:"
echo "  $SCRIPT_DIR/dist/protonvpn --version"
echo "  $SCRIPT_DIR/dist/protonvpn --help"
echo "  $SCRIPT_DIR/dist/proton-vpn-manager --version  # If daemon supports --version"
echo "  $SCRIPT_DIR/dist/proton-vpn-manager --help     # To see daemon options"
echo ""
