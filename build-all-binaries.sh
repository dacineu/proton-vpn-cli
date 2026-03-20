#!/usr/bin/env bash
#
# Build ALL standalone binaries for proton-vpn-cli project
#
# Artifacts produced:
#   1. dist/protonvpn              - Main CLI (all-in-one, includes tunnel support)
#   2. dist/proton-vpn-manager     - Daemon service (all-in-one)
#   3. multi-tunnel-namespace/dist/libvpnmanager-*.whl  - Library wheel (optional)
#
# All binaries embed Python interpreter and dependencies. No system Python needed.
#
# Prerequisites:
#   - Python 3.9+
#   - Virtual environment with ALL dependencies (including internal Proton packages)
#   - PyInstaller and build packages installed in venv
#
# Usage:
#   source .build-venv/bin/activate
#   ./build-all-binaries.sh
#
# Note: Internal Proton packages (proton-core, proton-vpn-api-core, etc.) must be
#       accessible via your pip configuration (see README.md).

set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$SCRIPT_DIR"

echo "================================================================================"
echo "  Proton VPN CLI - Complete Binary Build"
echo "================================================================================"
echo ""
echo "This script builds:"
echo "  1. protonvpn              - Full-featured CLI (connect, tunnel, etc.)"
echo "  2. proton-vpn-manager     - D-Bus daemon for multi-tunnel"
echo "  3. libvpnmanager-*.whl    - Pure Python library (wheel)"
echo ""
echo "Total estimated size: 150-250 MB"
echo ""
read -p "Press Enter to begin building... or Ctrl+C to cancel"

# Activate venv
if [ -z "$VIRTUAL_ENV" ]; then
    if [ -d ".build-venv" ]; then
        source .build-venv/bin/activate
    else
        echo "ERROR: Virtual environment not found. Create one first:"
        echo "  python -m venv .build-venv"
        echo "  source .build-venv/bin/activate"
        echo "  pip install -e . pyinstaller build"
        exit 1
    fi
fi

# Clean
echo ""
echo "Cleaning previous build artifacts..."
rm -rf dist/ build/ *.spec
mkdir -p dist

# ================================================================================
# Build 1: protonvpn (main CLI) - includes libvpnmanager for tunnel commands
# ================================================================================
echo ""
echo "================================================================================"
echo "Building 1/3: protonvpn (main CLI with full features)"
echo "================================================================================"

cat > protonvpn-cli.spec << 'PYSPEC'
# -*- mode: python ; coding: utf-8 -*-

block_cipher = None

a = Analysis(
    ['proton/vpn/cli/__init__.py'],
    pathex=[],
    binaries=[],
    datas=[
        # CLI commands and core
        ('proton/vpn/cli/commands', 'proton/vpn/cli/commands'),
        ('proton/vpn/cli/core', 'proton/vpn/cli/core'),
        # Include libvpnmanager package data
        ('multi-tunnel-namespace/src/libvpnmanager', 'libvpnmanager'),
    ],
    hiddenimports=[
        # Main CLI commands
        'proton.vpn.cli.commands.account',
        'proton.vpn.cli.commands.settings',
        'proton.vpn.cli.commands.servers',
        'proton.vpn.cli.commands.server',
        'proton.vpn.cli.commands.location_discovery',
        'proton.vpn.cli.commands.command_utils',
        'proton.vpn.cli.commands.tunnel',
        # Core
        'proton.vpn.cli.core.controller',
        'proton.vpn.cli.core.exception_handler',
        'proton.vpn.cli.core.exceptions',
        'proton.vpn.cli.core.run_async',
        'proton.vpn.cli.core.wait_for_current_tasks',
        # Dependencies
        'click', 'click.core', 'click.decorators', 'click.utils',
        'click.types', 'click.exceptions',
        'dbus_fast', 'dbus_fast.aio', 'dbus_fast.message',
        'dbus_fast.signature', 'dbus_fast.service', 'dbus_fast.constants',
        'tabulate', 'tabulate.table', 'tabulate.plain',
        'asyncio', 'importlib.metadata',
        # Proton packages
        'proton_core', 'proton_core.api',
        'proton_vpn_api_core', 'proton_vpn_api_core.api',
        'proton_vpn_api_core.api.client', 'proton_vpn_api_core.api.exceptions',
        'proton_keyring_linux', 'proton_keyring_linux.keyring',
        'proton_vpn_local_agent', 'proton_vpn_local_agent.client',
        # Libvpnmanager (for tunnel commands)
        'libvpnmanager',
        'libvpnmanager.client',
        'libvpnmanager.manager',
        'libvpnmanager.manager_v2',
        'libvpnmanager.routing',
        'libvpnmanager.routing.base',
        'libvpnmanager.routing.network_namespace',
        'libvpnmanager.sessions',
        'libvpnmanager.sessions.proton',
        'libvpnmanager.sessions.psiphon',
        'libvpnmanager.sessions.wireguard',
        'libvpnmanager.dbus',
        'libvpnmanager.dbus.client',
        'libvpnmanager.dbus.service',
        'libvpnmanager.dbus.constants',
        'libvpnmanager.adapters',
        'libvpnmanager.adapters.base',
        'libvpnmanager.adapters.dummy',
        # Note: proton adapter is external, not needed for CLI (uses D-Bus)
        'libvpnmanager.models',
        'libvpnmanager.models.config',
        'libvpnmanager.models.status',
        'libvpnmanager.models.exceptions',
        'libvpnmanager.models.exceptions',
        # Libvpnmanager dependencies
        'dbus_next', 'dbus_next.aio', 'dbus_next.service', 'dbus_next.constants',
        'pydantic', 'pydantic.main', 'pydantic.types', 'pydantic.fields',
        'asyncstdlib', 'asyncstdlib.functools', 'asyncstdlib.itertools',
        'pyroute2', 'pyroute2.config', 'pyroute2.netlink',
        'pyroute2.netlink.rtnl', 'pyroute2.netlink.rtnl.ifinfmsg',
        'pyroute2.netlink.rtnl.rtmsg', 'pyroute2.netlink.rtnl.ndmsg',
        'pyroute2.iproute', 'pyroute2.ndb', 'pyroute2.ndb.objects',
        'pyroute2.ndb.report',
        'systemd', 'systemd.daemon', 'systemd.journal',
    ],
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[
        'tkinter', 'matplotlib', 'numpy', 'scipy', 'pandas',
        'PIL', 'PyQt5', 'PySide2', 'wx',
        'test', 'unittest', 'pytest',
        'quart', 'flask', 'django', 'sqlalchemy',
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

pyinstaller protonvpn-cli.spec
PROTONVPN_SIZE=$(du -h dist/protonvpn | cut -f1)
echo "✓ Built protonvpn: $PROTONVPN_SIZE"

# ================================================================================
# Build 2: proton-vpn-manager (daemon) - also includes libvpnmanager
# ================================================================================
echo ""
echo "================================================================================"
echo "Building 2/3: proton-vpn-manager (daemon)"
echo "================================================================================"

cat > proton-vpn-manager.spec << 'PYSPEC'
# -*- mode: python ; coding: utf-8 -*-

block_cipher = None

a = Analysis(
    ['multi-tunnel-namespace/src/daemon/daemon.py'],
    pathex=['multi-tunnel-namespace/src'],
    binaries=[],
    datas=[
        ('multi-tunnel-namespace/src/libvpnmanager', 'libvpnmanager'),
        ('multi-tunnel-namespace/src/adapters/dummy_adapter', 'adapters/dummy_adapter'),
        ('multi-tunnel-namespace/src/adapters/proton_vpn_adapter', 'adapters/proton_vpn_adapter'),
        ('multi-tunnel-namespace/src/adapters/psiphon_adapter', 'adapters/psiphon_adapter'),
        ('multi-tunnel-namespace/src/adapters/wireguard_adapter', 'adapters/wireguard_adapter'),
    ],
    hiddenimports=[
        # Daemon
        'daemon.daemon',
        # Libvpnmanager
        'libvpnmanager', 'libvpnmanager.manager', 'libvpnmanager.manager_v2',
        'libvpnmanager.routing', 'libvpnmanager.routing.base',
        'libvpnmanager.routing.network_namespace',
        'libvpnmanager.sessions', 'libvpnmanager.sessions.base',
        'libvpnmanager.sessions.dummy', 'libvpnmanager.sessions.manager',
        'libvpnmanager.dbus', 'libvpnmanager.dbus.service',
        'libvpnmanager.dbus.client', 'libvpnmanager.dbus.constants',
        'libvpnmanager.adapters', 'libvpnmanager.adapters.base',
        'libvpnmanager.adapters.dummy',
        # Adapters (with adapters. prefix)
        'adapters.dummy_adapter',
        'adapters.dummy_adapter.adapter',
        'adapters.proton_vpn_adapter',
        'adapters.proton_vpn_adapter.adapter',
        'adapters.proton_vpn_adapter.sessions',
        'adapters.proton_vpn_adapter.sessions.proton',
        'adapters.psiphon_adapter',
        'adapters.psiphon_adapter.adapter',
        'adapters.psiphon_adapter.sessions',
        'adapters.psiphon_adapter.sessions.psiphon',
        'adapters.wireguard_adapter',
        'adapters.wireguard_adapter.adapter',
        'adapters.wireguard_adapter.sessions',
        'adapters.wireguard_adapter.sessions.wireguard',
        # Dependencies
        'asyncio', 'logging', 'signal', 'sys', 'pathlib',
        'dbus_next', 'dbus_next.aio', 'dbus_next.service', 'dbus_next.constants',
        'pydantic', 'pydantic.main', 'pydantic.types', 'pydantic.fields',
        'asyncstdlib', 'asyncstdlib.functools',
        'pyroute2', 'pyroute2.config', 'pyroute2.netlink',
        'pyroute2.netlink.rtnl', 'pyroute2.netlink.rtnl.ifinfmsg',
        'pyroute2.netlink.rtnl.rtmsg', 'pyroute2.netlink.rtnl.ndmsg',
        'pyroute2.iproute', 'pyroute2.ndb', 'pyroute2.ndb.objects',
        'pyroute2.ndb.report',
        'systemd', 'systemd.daemon', 'systemd.journal',
        # Proton packages (for proton adapter)
        'proton_core', 'proton_core.api',
        'proton_vpn_api_core', 'proton_vpn_api_core.api',
        'proton_vpn_api_core.api.client', 'proton_vpn_api_core.api.exceptions',
        'proton_keyring_linux', 'proton_keyring_linux.keyring',
        'proton_vpn_local_agent', 'proton_vpn_local_agent.client',
    ],
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[
        'tkinter', 'matplotlib', 'numpy', 'scipy', 'pandas',
        'PIL', 'PyQt5', 'PySide2', 'wx',
        'test', 'unittest', 'pytest',
        'click', 'tabulate', 'dbus_fast',  # Not used in daemon
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
    name='proton-vpn-manager',
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

pyinstaller proton-vpn-manager.spec
PROTONVPN_MANAGER_SIZE=$(du -h dist/proton-vpn-manager | cut -f1)
echo "✓ Built proton-vpn-manager: $PROTONVPN_MANAGER_SIZE"

# ================================================================================
# Build 3: libvpnmanager wheel (binary package for library)
# ================================================================================
echo ""
echo "================================================================================"
echo "Building 3/3: libvpnmanager wheel (library package)"
echo "================================================================================"

cd "$SCRIPT_DIR/multi-tunnel-namespace"
rm -rf dist/ build/ *.egg-info
source "$SCRIPT_DIR/.build-venv/bin/activate"
python -m build --wheel --no-isolation

cd "$SCRIPT_DIR"

WHEEL_NAME=$(ls -t multi-tunnel-namespace/dist/libvpnmanager-*.whl 2>/dev/null | head -1)
if [ -n "$WHEEL_NAME" ]; then
    WHEEL_SIZE=$(du -h "$WHEEL_NAME" | cut -f1)
    echo "✓ Built libvpnmanager wheel: $WHEEL_SIZE ($(basename "$WHEEL_NAME"))"
else
    echo "⚠ Warning: libvpnmanager wheel not found or failed to build"
fi

# ================================================================================
# Summary
# ================================================================================
echo ""
echo "================================================================================"
echo "  Build Complete!"
echo "================================================================================"
echo ""
echo "Artifacts:"
echo ""
ls -lh dist/ 2>/dev/null || echo "  (No binaries in dist/)"
echo ""
if [ -d "multi-tunnel-namespace/dist" ]; then
    echo "Wheel packages:"
    ls -lh multi-tunnel-namespace/dist/
fi
echo ""
echo "Files:"
echo "  • dist/protonvpn              - Main CLI executable"
echo "  • dist/proton-vpn-manager     - Daemon executable"
echo "  • multi-tunnel-namespace/dist/libvpnmanager-*.whl - Library wheel"
echo ""
echo "Quick install:"
echo "  sudo cp dist/protonvpn /usr/local/bin/"
echo "  sudo cp dist/proton-vpn-manager /usr/local/bin/"
echo "  # Install wheel if needed: pip install multi-tunnel-namespace/dist/*.whl"
echo ""
echo "System dependencies (must be present on target system):"
echo "  dbus, systemd, wireguard-tools, libdbus-1, libsystemd, libwireguard"
echo ""
echo "Verification:"
echo "  dist/protonvpn --version"
echo "  dist/protonvpn --help"
echo "  dist/proton-vpn-manager --help  # Shows daemon options (if any)"
echo ""
echo "Note: Both binaries include the full Python interpreter (~40 MB each) and"
echo "      all dependencies. They run on systems without Python installed."
echo "      Ensure the system has required shared libraries (dbus, systemd)."
echo ""
