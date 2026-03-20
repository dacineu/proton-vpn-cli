# -*- mode: python ; coding: utf-8 -*-
"""
PyInstaller spec for proton-vpn-manager daemon.

Builds a standalone binary that includes:
- daemon.daemon entry point
- libvpnmanager core library
- Adapter packages (proton_vpn_adapter, psiphon_adapter, wireguard_adapter, dummy_adapter)
- All dependencies (dbus_next, pydantic, pyroute2, etc.)
"""

block_cipher = None

a = Analysis(
    ['daemon/daemon.py'],
    pathex=['.'],  # current dir is src/
    binaries=[],
    datas=[
        # Include package data for libvpnmanager if needed (e.g., py.typed)
        ('libvpnmanager', 'libvpnmanager'),
        # Include adapters as data (they are pure Python)
        ('adapters/dummy_adapter', 'adapters/dummy_adapter'),
        ('adapters/proton_vpn_adapter', 'adapters/proton_vpn_adapter'),
        ('adapters/psiphon_adapter', 'adapters/psiphon_adapter'),
        ('adapters/wireguard_adapter', 'adapters/wireguard_adapter'),
    ],
    hiddenimports=[
        # Daemon
        'daemon', 'daemon.daemon',

        # Core libvpnmanager
        'libvpnmanager',
        'libvpnmanager.manager',
        'libvpnmanager.manager_v2',
        'libvpnmanager.routing',
        'libvpnmanager.routing.base',
        'libvpnmanager.routing.network_namespace',
        'libvpnmanager.sessions',
        'libvpnmanager.sessions.base',
        'libvpnmanager.sessions.dummy',
        'libvpnmanager.sessions.manager',
        'libvpnmanager.models',
        'libvpnmanager.models.tunnel',
        'libvpnmanager.models.config',
        'libvpnmanager.models.status',
        'libvpnmanager.models.exceptions',
        'libvpnmanager.dbus',
        'libvpnmanager.dbus.service',
        'libvpnmanager.dbus.client',
        'libvpnmanager.adapters',
        'libvpnmanager.adapters.base',
        'libvpnmanager.adapters.dummy',

        # Adapters (all submodules need to be included) - using adapters. prefix
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
        'dbus_next',
        'dbus_next.aio',
        'dbus_next.service',
        'dbus_next.constants',
        'dbus_next.errors',
        'pydantic',
        'pydantic.main',
        'pydantic.validators',
        'pydantic.fields',
        'pydantic.networks',
        'asyncstdlib',
        'pyroute2',
        'pyroute2.ndb',
        'pyroute2.netns',
        'asyncio',
        'json',
        'logging',
        'signal',
        'sys',
        'pathlib',
        'os',
    ],
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[
        # Unnecessary large modules
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
        # CLI-specific
        'click',
        'tabulate',
        # Proton packages (not directly used by daemon; they're used via adapter)
        # but if proton_vpn_adapter imports them, we need them. Keep them.
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
