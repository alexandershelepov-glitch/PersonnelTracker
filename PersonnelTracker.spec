# -*- mode: python ; coding: utf-8 -*-

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

app = BUNDLE(
    coll,
    name="PersonnelTracker.app",
    icon=None,
    bundle_identifier="ru.personneltracker.app",
    version="0.9.2",
    info_plist={
        "CFBundleDisplayName": "Учёт личного состава",
        "CFBundleName": "PersonnelTracker",
        "NSHighResolutionCapable": True,
    },
)
