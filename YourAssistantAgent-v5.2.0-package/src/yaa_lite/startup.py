from __future__ import annotations

import os
import sys

RUN_KEY = r"Software\Microsoft\Windows\CurrentVersion\Run"
VALUE_NAME = "YourAssistantAgent"


def apply_startup_mode(mode: str) -> None:
    """Apply Windows startup preference. No-op on other platforms."""
    if os.name != "nt":
        return
    import winreg
    with winreg.OpenKey(winreg.HKEY_CURRENT_USER, RUN_KEY, 0, winreg.KEY_SET_VALUE) as key:
        if mode == "off":
            try:
                winreg.DeleteValue(key, VALUE_NAME)
            except FileNotFoundError:
                pass
            return
        exe = sys.executable
        arg = " --start-in-tray" if mode == "tray" else ""
        winreg.SetValueEx(key, VALUE_NAME, 0, winreg.REG_SZ, f'"{exe}"{arg}')
