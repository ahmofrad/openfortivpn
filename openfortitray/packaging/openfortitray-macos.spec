# -*- mode: python ; coding: utf-8 -*-
"""PyInstaller spec for macOS (SPEC.md §11).

Expects vendored binary in packaging/vendor/macos/:
  - openfortivpn

Build: pyinstaller packaging/openfortitray-macos.spec --noconfirm
"""

from pathlib import Path

block_cipher = None

project_root = Path.cwd()
vendor_dir = project_root / 'packaging' / 'vendor' / 'macos'

binaries = []

if vendor_dir.exists():
    for f in vendor_dir.iterdir():
        if f.is_file():
            binaries.append((str(f), '.'))

a = Analysis(
    [str(project_root / 'src' / 'openfortitray' / '__main__.py')],
    pathex=[str(project_root / 'src')],
    binaries=binaries,
    datas=[],
    hiddenimports=[
        'keyring.backends.macOS',
        'keyring.backends.chainer',
    ],
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=['tkinter', 'unittest', 'pydoc'],
    cipher=block_cipher,
    noarchive=False,
)

pyz = PYZ(a.pure, a.zipped_data, cipher=block_cipher)

exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name='OpenFortiTray',
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=False,
    console=False,
)

coll = COLLECT(
    exe,
    a.binaries,
    a.zipfiles,
    a.datas,
    strip=False,
    upx=False,
    upx_exclude=[],
    name='OpenFortiTray',
)
