# -*- mode: python ; coding: utf-8 -*-
from pathlib import Path
from PyInstaller.utils.hooks import collect_all

root = Path(SPECPATH)
datas = []
for folder in ("models", "runtime", "assets", "licenses", "browser_extension"):
    p = root / folder
    if p.exists():
        datas.append((str(p), folder))
for file_name in ("THIRD_PARTY_SMOLAGENTS.md", "THIRD_PARTY_HAMMER.md", "THIRD_PARTY_QWEN.md", "THIRD_PARTY_VOICE.md"):
    p = root / file_name
    if p.exists():
        datas.append((str(p), "."))

sd_datas, sd_binaries, sd_hidden = collect_all("sounddevice")
datas += sd_datas
binaries = list(sd_binaries)

hiddenimports = [
    "yaa_lite",
    "yaa_lite.main",
    "yaa_lite.personal_assistant_v220",
    "yaa_lite.ui.app",
    "PIL",
    "pystray",
    "sounddevice",
    "yaa_lite.startup",
    "yaa_lite.voice.service",
    "yaa_lite.browser_bridge.server",
    "yaa_lite.backup.google_drive",
    "yaa_lite.backup.service",
    "yaa_lite.security.manager",
    "yaa_lite.ui.tray",
    "yaa_lite.ui.unlock_dialog",
    "yaa_lite.ui.setup_wizard",
    "yaa_lite.ui.backup_view",
    "yaa_lite.ui.tasks_view",
    "yaa_lite.ui.facebook_view",
    "yaa_lite.ui.home_view",
    "yaa_lite.ui.chat_window",
    "yaa_lite.ui.activity_view",
    "yaa_lite.ui.settings_view",
    "yaa_lite.ui.advanced_view",
    "yaa_lite.ui.resources",
    "yaa_lite.ui.i18n",
    "yaa_lite.ai.engine",
    "yaa_lite.ai.profiles",
    "yaa_lite.ai.runtime",
    "yaa_lite.storage.db",
    "yaa_lite.agent.orchestrator",
    "yaa_lite.agent.hammer_agent",
    "yaa_lite.agent.tools",
    "yaa_lite.agent.facebook_service",
    "yaa_lite.agent.legacy_smart",
    "yaa_lite.facebook_backend.facebook",
    "yaa_lite.facebook_backend.browser_discovery",
    "yaa_lite.facebook_backend.paths",
    "yaa_lite.facebook_backend.share_outcome",
    "yaa_lite.agent.smol_contract",
    "playwright.sync_api",
] + list(sd_hidden)

a = Analysis(
    [str(root / "launcher.py")],
    pathex=[str(root / "src")],
    binaries=binaries,
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
