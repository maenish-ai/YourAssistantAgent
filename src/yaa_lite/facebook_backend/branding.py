from __future__ import annotations

import sys
from pathlib import Path


def package_root() -> Path:
    if hasattr(sys, "_MEIPASS"):
        return Path(sys._MEIPASS)
    # src/yaa_lite/facebook_backend/branding.py -> repo root
    return Path(__file__).resolve().parents[3]


def asset_path(name: str) -> Path:
    return package_root() / "assets" / name
