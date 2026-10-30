from __future__ import annotations

import os

LIGHT = {
    "BG": "#f3f5fb", "PANEL": "#ffffff", "TEXT": "#182238", "MUTED": "#61708a",
    "ACCENT": "#6750d8", "BUTTON": "#6750d8", "ACCENT_HOVER": "#543fc0", "BORDER": "#e1e6f1",
    "USER_BUBBLE": "#ece8ff", "AI_BUBBLE": "#ffffff", "SIDEBAR": "#eaf0fa",
    "SIDEBAR_HOVER": "#dfe6f4", "SIDEBAR_ACTIVE": "#e0dafa", "SUCCESS": "#087f5b",
    "DANGER": "#b42318", "WARNING": "#b54708", "INPUT": "#ffffff",
}
DARK = {
    "BG": "#0c111e", "PANEL": "#171f31", "TEXT": "#eef2ff", "MUTED": "#a2afc9",
    "ACCENT": "#b2a0ff", "BUTTON": "#7154d1", "ACCENT_HOVER": "#6747bf", "BORDER": "#2c374e",
    "USER_BUBBLE": "#2f2853", "AI_BUBBLE": "#171f31", "SIDEBAR": "#101829",
    "SIDEBAR_HOVER": "#202b43", "SIDEBAR_ACTIVE": "#332d56", "SUCCESS": "#5cddb3",
    "DANGER": "#ff9aab", "WARNING": "#fdbf68", "INPUT": "#171f31",
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
