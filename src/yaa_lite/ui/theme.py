from __future__ import annotations

import os

LIGHT = {
    "BG": "#f7f7f8", "PANEL": "#ffffff", "TEXT": "#202123", "MUTED": "#6b7280",
    "ACCENT": "#5b5bd6", "ACCENT_HOVER": "#4b4bc4", "BORDER": "#e5e7eb",
    "USER_BUBBLE": "#eef2ff", "AI_BUBBLE": "#ffffff", "SIDEBAR": "#f0f1f4",
    "SIDEBAR_HOVER": "#e5e7eb", "SIDEBAR_ACTIVE": "#dddff7", "SUCCESS": "#087f5b",
    "DANGER": "#b42318", "WARNING": "#b54708", "INPUT": "#ffffff",
}
DARK = {
    "BG": "#171717", "PANEL": "#212121", "TEXT": "#f4f4f5", "MUTED": "#a1a1aa",
    "ACCENT": "#8b8bf5", "ACCENT_HOVER": "#7777e8", "BORDER": "#3f3f46",
    "USER_BUBBLE": "#2b2b3b", "AI_BUBBLE": "#212121", "SIDEBAR": "#111111",
    "SIDEBAR_HOVER": "#2b2b2b", "SIDEBAR_ACTIVE": "#303047", "SUCCESS": "#34d399",
    "DANGER": "#f97066", "WARNING": "#fdb022", "INPUT": "#2b2b2b",
}


def _system_dark() -> bool:
    if os.name != "nt":
        return False
    try:
        import winreg
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER, r"Software\Microsoft\Windows\CurrentVersion\Themes\Personalize") as k:
            value, _ = winreg.QueryValueEx(k, "AppsUseLightTheme")
        return int(value) == 0
    except Exception:
        return False


def resolve(mode: str) -> str:
    if mode == "dark":
        return "dark"
    if mode == "light":
        return "light"
    return "dark" if _system_dark() else "light"


def apply(mode: str) -> str:
    palette = DARK if resolve(mode) == "dark" else LIGHT
    globals().update(palette)
    return resolve(mode)


apply("system")
