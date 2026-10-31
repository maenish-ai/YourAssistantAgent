from __future__ import annotations

import sys
from pathlib import Path


def bundle_root() -> Path:
    """Return the PyInstaller bundle root or the repository root from source."""
    if getattr(sys, "frozen", False):
        meipass = getattr(sys, "_MEIPASS", None)
        if meipass:
            return Path(meipass).resolve()
        return Path(sys.executable).resolve().parent
    return Path(__file__).resolve().parents[3]


def asset_path(name: str) -> Path:
    return bundle_root() / "assets" / name
