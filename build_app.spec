# -*- mode: python ; coding: utf-8 -*-
from pathlib import Path

root = Path(SPECPATH)
datas = []
for folder in ("models", "runtime"):
    p = root / folder
    if p.exists():
        datas.append((str(p), folder))

a = Analysis(
    [str(root / "src" / "yaa_lite" / "main.py")],
    pathex=[str(root / "src")],
    binaries=[],
    datas=datas,
    hiddenimports=["yaa_lite", "yaa_lite.ui.app", "yaa_lite.ui.chat_window"],
    hookspath=[], hooksconfig={}, runtime_hooks=[], excludes=["PySide6", "numpy", "pandas", "matplotlib"],
    noarchive=False,
)
pyz = PYZ(a.pure)
exe = EXE(pyz, a.scripts, [], exclude_binaries=True, name="YourAssistantAgent", debug=False, bootloader_ignore_signals=False, strip=False, upx=False, console=False)
coll = COLLECT(exe, a.binaries, a.datas, strip=False, upx=False, upx_exclude=[], name="YourAssistantAgent")
