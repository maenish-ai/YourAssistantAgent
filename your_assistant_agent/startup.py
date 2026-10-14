from __future__ import annotations

import os
import sys
from pathlib import Path

APP_NAME = "YourAssistantAgent"
LEGACY_APP_NAMES = ("SatelliteAgent",)


def startup_dir() -> Path:
    appdata = os.environ.get("APPDATA")
    if not appdata:
        raise RuntimeError("APPDATA is not available")
    return Path(appdata) / "Microsoft" / "Windows" / "Start Menu" / "Programs" / "Startup"


def startup_file() -> Path:
    return startup_dir() / f"{APP_NAME}.cmd"


def legacy_startup_files() -> list[Path]:
    return [startup_dir() / f"{name}.cmd" for name in LEGACY_APP_NAMES]


def is_enabled() -> bool:
    if os.name != "nt":
        return False
    return startup_file().exists()


def _remove_legacy_startup_files() -> None:
    for legacy in legacy_startup_files():
        try:
            legacy.unlink()
        except FileNotFoundError:
            pass
        except OSError:
            pass


def set_enabled(enabled: bool):
    if os.name != "nt":
        raise RuntimeError("Windows startup integration is only available on Windows")
    p = startup_file()
    p.parent.mkdir(parents=True, exist_ok=True)
    if not enabled:
        try:
            p.unlink()
        except FileNotFoundError:
            pass
        _remove_legacy_startup_files()
        return

    if getattr(sys, "frozen", False):
        command = f'@echo off\r\nstart "" "{Path(sys.executable)}" --minimized\r\n'
    else:
        project_root = Path(__file__).resolve().parents[1]
        run_bat = project_root / "run_windows.bat"
        command = f'@echo off\r\nstart "" "{run_bat}" --minimized\r\n'
    p.write_text(command, encoding="utf-8")
    _remove_legacy_startup_files()


def migrate_legacy_startup() -> None:
    """Preserve an enabled Startup setting across the v0.1 product rename."""
    if os.name != "nt" or startup_file().exists():
        return
    try:
        if any(p.exists() for p in legacy_startup_files()):
            set_enabled(True)
    except Exception:
        # Startup migration is best-effort and must not block app launch.
        pass
