# -*- mode: python ; coding: utf-8 -*-

block_cipher = None

a = Analysis(
    ['proton/vpn/cli/__init__.py'],
    pathex=[],
    binaries=[],
    datas=[
        ('proton/vpn/cli/commands', 'proton/vpn/cli/commands'),
        ('proton/vpn/cli/core', 'proton/vpn/cli/core'),
    ],
    hiddenimports=[
        'proton.vpn.cli.commands.account',
        'proton.vpn.cli.commands.settings',
        'proton.vpn.cli.commands.servers',
        'proton.vpn.cli.commands.server',
        'proton.vpn.cli.commands.location_discovery',
        'proton.vpn.cli.commands.command_utils',
        'proton.vpn.cli.commands.tunnel',
        'proton.vpn.cli.core.controller',
        'proton.vpn.cli.core.exception_handler',
        'proton.vpn.cli.core.exceptions',
        'proton.vpn.cli.core.run_async',
        'proton.vpn.cli.core.wait_for_current_tasks',
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
        'asyncio',
        'importlib.metadata',
    ],
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[
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
    ],
    win_no_prefer_redirects=False,
    win_private_assemblies=False,
    cipher=block_cipher,
    noarchive=False,
)

for mod in ['proton_core', 'proton_vpn_api_core', 'proton_keyring_linux', 'proton_vpn_local_agent']:
    try:
        import importlib.util
        spec = importlib.util.find_spec(mod)
        if spec:
            a.pure.append((mod.replace('_', '.'), spec))
    except:
        pass

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
