# -*- mode: python ; coding: utf-8 -*-
"""PyInstaller spec for Linux (SPEC.md §11).

Expects vendored binary in packaging/vendor/linux/:
  - openfortivpn

Build: pyinstaller packaging/openfortitray-linux.spec --noconfirm
"""

from pathlib import Path

block_cipher = None

project_root = Path.cwd()
vendor_dir = project_root / 'packaging' / 'vendor' / 'linux'

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
        'keyring.backends.SecretService',
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
    name='openfortitray',
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    console=True,
)

coll = COLLECT(
    exe,
    a.binaries,
    a.zipfiles,
    a.datas,
    strip=False,
    upx=True,
    upx_exclude=[],
    name='OpenFortiTray',
)
