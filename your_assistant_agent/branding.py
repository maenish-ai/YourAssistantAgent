from __future__ import annotations

import sys
from pathlib import Path

from PySide6.QtGui import QIcon, QPixmap


def package_root() -> Path:
    if hasattr(sys, "_MEIPASS"):
        return Path(sys._MEIPASS)
    return Path(__file__).resolve().parent.parent


def asset_path(name: str) -> Path:
    return package_root() / "assets" / name


def icon_path() -> Path:
    return asset_path("app_icon.png")


def splash_path() -> Path:
    return asset_path("splash.png")


def window_icon() -> QIcon:
    path = icon_path()
    return QIcon(str(path)) if path.exists() else QIcon()


def pixmap(name: str) -> QPixmap:
    path = asset_path(name)
    return QPixmap(str(path)) if path.exists() else QPixmap()
