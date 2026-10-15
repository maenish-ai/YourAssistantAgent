from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def test_stable_absolute_launcher_is_used():
    launcher = (ROOT / "launcher.py").read_text(encoding="utf-8")
    spec = (ROOT / "build_app.spec").read_text(encoding="utf-8")
    assert "from yaa_lite.main import main" in launcher
    assert 'root / "launcher.py"' in spec
    assert 'src" / "yaa_lite" / "main.py"' not in spec


def test_original_branding_is_packaged_everywhere():
    for name in (
        "icon.ico",
        "brand_mark.png",
        "brand_mark_64.png",
        "brand_mark_128.png",
        "brand_mark_256.png",
        "installer_wizard.bmp",
        "installer_small.bmp",
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
    assert "Your Assistant Agent" in version_info
    assert "2.0.0.0" in version_info
    spec = (ROOT / "build_app.spec").read_text(encoding="utf-8")
    assert "version_info.txt" in spec


def test_only_one_active_workflow_is_shipped():
    workflows = sorted((ROOT / ".github" / "workflows").glob("*.yml"))
    assert [p.name for p in workflows] == ["build-windows.yml"]
