from pathlib import Path
import re

ROOT = Path(__file__).resolve().parents[1]


def test_stable_absolute_launcher_is_used():
    launcher = (ROOT / "launcher.py").read_text(encoding="utf-8")
    spec = (ROOT / "build_app.spec").read_text(encoding="utf-8")
    assert "from yaa_lite.main import main" in launcher
    assert 'root / "launcher.py"' in spec
    assert 'src" / "yaa_lite" / "main.py"' not in spec


def test_original_branding_is_packaged_everywhere():
    for name in (
        "icon.ico", "brand_mark.png", "brand_mark_64.png", "brand_mark_128.png",
        "brand_mark_256.png", "installer_wizard.bmp", "installer_small.bmp",
    ):
        assert (ROOT / "assets" / name).exists(), name
    spec = (ROOT / "build_app.spec").read_text(encoding="utf-8")
    installer = (ROOT / "installer" / "YourAssistantAgent.iss").read_text(encoding="utf-8")
    assert '"assets"' in spec
    assert "icon.ico" in spec
    assert "SetupIconFile=..\\assets\\icon.ico" in installer
    assert "WizardImageFile=..\\assets\\installer_wizard.bmp" in installer
    assert "WizardSmallImageFile=..\\assets\\installer_small.bmp" in installer
    assert "UninstallDisplayIcon={app}\\{#MyAppExeName}" in installer


def test_windows_version_metadata_is_present():
    version_info = (ROOT / "version_info.txt").read_text(encoding="utf-8")
    installer = (ROOT / "installer" / "YourAssistantAgent.iss").read_text(encoding="utf-8")
    assert "Your Assistant Agent" in version_info
    version = re.search(r'^#define MyAppVersion "(\d+\.\d+\.\d+)"', installer, re.M)
    assert version, "Installer version is missing"
    assert f"{version.group(1)}.0" in version_info
    spec = (ROOT / "build_app.spec").read_text(encoding="utf-8")
    assert "version_info.txt" in spec


def test_android_and_windows_have_separate_nonduplicated_workflows():
    workflows = sorted((ROOT / ".github" / "workflows").glob("*.yml"))
    assert [p.name for p in workflows] == ["build-android.yml", "build-windows.yml"]
    android, windows = [p.read_text(encoding='utf-8') for p in workflows]
    assert ':app:assembleDebug' in android and ':app:assembleDebug' not in windows
    assert 'build_app.spec' in windows and 'build_app.spec' not in android
    assert 'workflow_dispatch:' in android and 'workflow_dispatch:' in windows
