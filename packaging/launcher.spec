# -*- mode: python ; coding: utf-8 -*-
# PyInstaller spec for 小说世界书 GUI launcher (Windows).
# Build: scripts/build_launcher.ps1

import sys
from pathlib import Path

block_cipher = None
spec_dir = Path(SPECPATH).resolve()
project_root = spec_dir.parent
ui_src = project_root / "src" / "novel_world" / "launcher" / "ui"
icon_ico = project_root / "packaging" / "assets" / "launcher-icon.ico"

datas = [
    (str(ui_src), "novel_world/launcher/ui"),
    (str(icon_ico), "packaging/assets"),
]

a = Analysis(
    [str(project_root / "src" / "novel_world" / "launcher" / "__main__.py")],
    pathex=[str(project_root / "src")],
    binaries=[],
    datas=datas,
    hiddenimports=["webview", "clr"],
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[],
    win_no_prefer_redirects=False,
    win_private_assemblies=False,
    cipher=block_cipher,
    noarchive=False,
)

pyz = PYZ(a.pure, a.zipped_data, cipher=block_cipher)

exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name="小说世界书启动器",
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    console=False,
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
    icon=str(icon_ico) if icon_ico.is_file() else None,
)

coll = COLLECT(
    exe,
    a.binaries,
    a.zipfiles,
    a.datas,
    strip=False,
    upx=True,
    upx_exclude=[],
    name="小说世界书启动器",
)
