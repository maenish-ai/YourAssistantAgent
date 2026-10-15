# -*- mode: python ; coding: utf-8 -*-
from pathlib import Path

root = Path(SPECPATH)
datas = []
for folder in ("models", "runtime", "assets"):
    p = root / folder
    if p.exists():
        datas.append((str(p), folder))

a = Analysis(
    [str(root / "launcher.py")],
    pathex=[str(root / "src")],
    binaries=[],
    datas=datas,
    hiddenimports=[
        "yaa_lite",
        "yaa_lite.main",
        "yaa_lite.ui.app",
        "yaa_lite.ui.agent_picker",
        "yaa_lite.ui.chat_window",
        "yaa_lite.ui.resources",
        "yaa_lite.ai.engine",
        "yaa_lite.ai.profiles",
        "yaa_lite.ai.runtime",
        "yaa_lite.storage.db",
    ],
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=["PySide6", "numpy", "pandas", "matplotlib"],
    noarchive=False,
)
pyz = PYZ(a.pure)
exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name="YourAssistantAgent",
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=False,
    console=False,
    icon=str(root / "assets" / "icon.ico"),
    version=str(root / "version_info.txt"),
)
coll = COLLECT(
    exe,
    a.binaries,
    a.datas,
    strip=False,
    upx=False,
    upx_exclude=[],
    name="YourAssistantAgent",
)
