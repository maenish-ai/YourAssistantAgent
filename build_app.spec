# -*- mode: python ; coding: utf-8 -*-
from pathlib import Path

root = Path(SPECPATH)
datas = []
for folder in ("models", "runtime", "assets", "licenses"):
    p = root / folder
    if p.exists():
        datas.append((str(p), folder))
for file_name in ("THIRD_PARTY_SMOLAGENTS.md",):
    p = root / file_name
    if p.exists():
        datas.append((str(p), "."))

hiddenimports = [
    "yaa_lite",
    "yaa_lite.main",
    "yaa_lite.ui.app",
    "yaa_lite.ui.agent_picker",
    "yaa_lite.ui.chat_window",
    "yaa_lite.ui.activity_view",
    "yaa_lite.ui.settings_view",
    "yaa_lite.ui.advanced_view",
    "yaa_lite.ui.resources",
    "yaa_lite.ai.engine",
    "yaa_lite.ai.profiles",
    "yaa_lite.ai.runtime",
    "yaa_lite.storage.db",
    "yaa_lite.agent.orchestrator",
    "yaa_lite.agent.tools",
    "yaa_lite.agent.facebook_service",
    "yaa_lite.agent.legacy_smart",
    "yaa_lite.facebook_backend.facebook",
    "yaa_lite.facebook_backend.browser_discovery",
    "yaa_lite.facebook_backend.paths",
    "yaa_lite.facebook_backend.share_outcome",
    "yaa_lite.agent.smol_contract",
    "playwright.sync_api",
]

a = Analysis(
    [str(root / "launcher.py")],
    pathex=[str(root / "src")],
    binaries=[],
    datas=datas,
    hiddenimports=hiddenimports,
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=["PySide6", "numpy", "pandas", "matplotlib", "torch", "torchvision"],
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
