# -*- mode: python ; coding: utf-8 -*-
"""PyInstaller spec for the portable Windows build (onedir).

Mirrors PersonnelTracker.spec but stops at COLLECT: the Windows artifact is a
plain folder (PersonnelTracker/PersonnelTracker.exe) that runs without Python,
PySide6 or any development tooling. There is intentionally no BUNDLE, no
onefile archive and no installer.
"""

block_cipher = None


a = Analysis(
    ["app.py"],
    pathex=[],
    binaries=[],
    datas=[],
    hiddenimports=[],
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[],
    noarchive=False,
    optimize=0,
)
pyz = PYZ(a.pure)

exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name="PersonnelTracker",
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=False,
    console=False,
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
)

coll = COLLECT(
    exe,
    a.binaries,
    a.datas,
    strip=False,
    upx=False,
    upx_exclude=[],
    name="PersonnelTracker",
)
