# -*- mode: python ; coding: utf-8 -*-
"""PyInstaller spec for Windows -- onefile mode (single .exe, no _internal).

Build: pyinstaller packaging/openfortitray-windows.spec --noconfirm
"""

import sys
from pathlib import Path

block_cipher = None

project_root = Path.cwd()
vendor_dir = project_root / 'packaging' / 'vendor' / 'windows'

# Collect all vendored DLLs/exes + icon
datas = [('app_icon.png', '.'), ('app_icon.ico', '.')]
binaries = []

if vendor_dir.exists():
    for f in vendor_dir.iterdir():
        if f.suffix.lower() in ('.dll', '.exe'):
            binaries.append((str(f), '.'))

a = Analysis(
    [str(project_root / 'src' / 'openfortitray' / '__main__.py')],
    pathex=[str(project_root / 'src')],
    binaries=binaries,
    datas=datas,
    hiddenimports=[
        'keyring.backends.Windows',
        'keyring.backends.chainer',
    ],
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[
        'tkinter',
        'unittest',
        'pydoc',
        'PySide6.Qt3D',
        'PySide6.QtCharts',
        'PySide6.QtDataVisualization',
        'PySide6.QtLocation',
        'PySide6.QtMultimedia',
        'PySide6.QtNetworkAuth',
        'PySide6.QtPositioning',
        'PySide6.QtQml',
        'PySide6.QtQuick',
        'PySide6.QtQuick3D',
        'PySide6.QtQuickWidgets',
        'PySide6.QtRemoteObjects',
        'PySide6.QtScxml',
        'PySide6.QtSensors',
        'PySide6.QtSerialPort',
        'PySide6.QtSpatialAudio',
        'PySide6.QtSql',
        'PySide6.QtSvg',
        'PySide6.QtTest',
        'PySide6.QtTextToSpeech',
        'PySide6.QtUiTools',
        'PySide6.QtWebChannel',
        'PySide6.QtWebEngineCore',
        'PySide6.QtWebEngineQuick',
        'PySide6.QtWebEngineWidgets',
        'PySide6.QtWebSockets',
        'PySide6.QtXml',
        'PySide6.QtPdf',
        'PySide6.QtPdfWidgets',
        'PySide6.QtOpenGL',
        'PySide6.QtOpenGLWidgets',
        'PySide6.QtDesigner',
        'PySide6.QtHelp',
        'PySide6.QtBluetooth',
        'PySide6.QtNfc',
        'PySide6.QtQuickControls2',
        'PySide6.QtQuickTemplates2',
        'PySide6.QtShaderTools',
        'PySide6.QtPrintSupport',
        'PySide6.QtImageFormats',
        'shiboken6.shiboken6',
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
    name='OpenFortiTray',
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    upx_exclude=[
        'vcruntime140.dll',
        'VCRUNTIME140.dll',
        'python3.dll',
    ],
    runtime_tmpdir=None,
    console=False,
    disable_windowed_traceback=False,
    icon=str(project_root / 'app_icon.ico'),
)
