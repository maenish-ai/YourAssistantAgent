from __future__ import annotations

import os
import shutil
from pathlib import Path

APP_NAME = "YourAssistantAgent"
LEGACY_APP_NAMES = ("SatelliteAgent",)


def _base_data_dir() -> Path:
    if os.name == "nt":
        return Path(os.environ.get("LOCALAPPDATA", Path.home() / "AppData" / "Local"))
    return Path.home() / ".local" / "share"


def _migrate_legacy_profile(path: Path) -> None:
    """Best-effort one-time copy of v0.1 data after the product rename.

    The old folder is left intact as a backup so upgrading the branding does not
    destroy the user's database or dedicated Facebook browser session.
    """
    if path.exists():
        return
    base = _base_data_dir()
    for legacy_name in LEGACY_APP_NAMES:
        legacy = base / legacy_name
        if not legacy.exists() or legacy == path:
            continue
        try:
            shutil.copytree(legacy, path)
            return
        except Exception:
            # Branding migration must never prevent the application from starting.
            pass


def app_data_dir() -> Path:
    path = _base_data_dir() / APP_NAME
    _migrate_legacy_profile(path)
    path.mkdir(parents=True, exist_ok=True)
    return path


def db_path() -> Path:
    return app_data_dir() / "agent.db"


def browser_profile_dir() -> Path:
    p = app_data_dir() / "facebook_profile"
    p.mkdir(parents=True, exist_ok=True)
    return p


def log_dir() -> Path:
    p = app_data_dir() / "logs"
    p.mkdir(parents=True, exist_ok=True)
    return p
