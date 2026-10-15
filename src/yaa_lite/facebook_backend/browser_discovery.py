from __future__ import annotations

import os
import re
import shutil
from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class BrowserInfo:
    name: str
    executable: Path
    engine: str
    support: str
    source: str = "system"

    @property
    def key(self) -> str:
        return str(self.executable)


def _extract_executable_from_command(command: str) -> str:
    """Extract an .exe path from a Windows shell/open command."""
    text = (command or "").strip()
    if not text:
        return ""
    quoted = re.match(r'^\s*"([^"]+?\.exe)"', text, flags=re.I)
    if quoted:
        return quoted.group(1)
    plain = re.match(r"^\s*([^\r\n]+?\.exe)(?:\s|$)", text, flags=re.I)
    return plain.group(1).strip() if plain else ""


def classify_browser_executable(path: str | Path, display_name: str = "") -> tuple[str, str]:
    """Return (engine, support) for a browser executable.

    support values:
      full         - preferred and routinely compatible with Playwright Chromium
      experimental - detected Chromium-family/unknown browser; may work
      unsupported  - known non-Chromium browser for this automation backend
    """
    exe = Path(path).name.casefold()
    name = (display_name or "").casefold()

    if exe in {"chrome.exe", "msedge.exe", "chromium.exe"}:
        return "chromium", "full"
    if exe in {"brave.exe", "vivaldi.exe", "opera.exe", "opera_gx.exe", "browser.exe"}:
        return "chromium", "experimental"
    if exe == "firefox.exe" or "firefox" in name:
        return "firefox", "unsupported"

    chromium_hints = ("chrome", "chromium", "edge", "brave", "vivaldi", "opera")
    if any(hint in exe or hint in name for hint in chromium_hints):
        return "chromium", "experimental"
    return "unknown", "experimental"


def _registry_browsers() -> list[tuple[str, Path]]:
    if os.name != "nt":
        return []
    try:
        import winreg
    except Exception:
        return []

    found: list[tuple[str, Path]] = []
    roots = (winreg.HKEY_CURRENT_USER, winreg.HKEY_LOCAL_MACHINE)
    key_paths = (
        r"SOFTWARE\Clients\StartMenuInternet",
        r"SOFTWARE\WOW6432Node\Clients\StartMenuInternet",
    )

    for root in roots:
        for key_path in key_paths:
            try:
                with winreg.OpenKey(root, key_path) as root_key:
                    count, _, _ = winreg.QueryInfoKey(root_key)
                    for i in range(count):
                        try:
                            sub_name = winreg.EnumKey(root_key, i)
                            with winreg.OpenKey(root_key, sub_name) as browser_key:
                                try:
                                    display_name = str(winreg.QueryValue(browser_key, None) or sub_name)
                                except Exception:
                                    display_name = sub_name
                            command_key = key_path + "\\" + sub_name + r"\shell\open\command"
                            with winreg.OpenKey(root, command_key) as cmd_key:
                                command = str(winreg.QueryValue(cmd_key, None) or "")
                            exe = _extract_executable_from_command(command)
                            if exe:
                                found.append((display_name, Path(os.path.expandvars(exe))))
                        except Exception:
                            continue
            except Exception:
                continue
    return found


def _common_browser_paths() -> list[tuple[str, Path]]:
    if os.name != "nt":
        return []

    env = os.environ
    pf = Path(env.get("PROGRAMFILES", ""))
    pfx86 = Path(env.get("PROGRAMFILES(X86)", ""))
    local = Path(env.get("LOCALAPPDATA", ""))

    raw = [
        ("Google Chrome", pf / "Google/Chrome/Application/chrome.exe"),
        ("Google Chrome", pfx86 / "Google/Chrome/Application/chrome.exe"),
        ("Google Chrome", local / "Google/Chrome/Application/chrome.exe"),
        ("Microsoft Edge", pf / "Microsoft/Edge/Application/msedge.exe"),
        ("Microsoft Edge", pfx86 / "Microsoft/Edge/Application/msedge.exe"),
        ("Microsoft Edge", local / "Microsoft/Edge/Application/msedge.exe"),
        ("Brave", pf / "BraveSoftware/Brave-Browser/Application/brave.exe"),
        ("Brave", pfx86 / "BraveSoftware/Brave-Browser/Application/brave.exe"),
        ("Brave", local / "BraveSoftware/Brave-Browser/Application/brave.exe"),
        ("Vivaldi", local / "Vivaldi/Application/vivaldi.exe"),
        ("Vivaldi", pf / "Vivaldi/Application/vivaldi.exe"),
        ("Opera", local / "Programs/Opera/opera.exe"),
        ("Opera GX", local / "Programs/Opera GX/opera.exe"),
        ("Mozilla Firefox", pf / "Mozilla Firefox/firefox.exe"),
        ("Mozilla Firefox", pfx86 / "Mozilla Firefox/firefox.exe"),
    ]
    return raw


def discover_installed_browsers() -> list[BrowserInfo]:
    """Discover browsers registered/installed on Windows.

    Registry discovery allows third-party browsers to appear even when their
    install directory is not one of the common Chrome/Edge paths.
    """
    raw: list[tuple[str, Path, str]] = []
    raw.extend((name, path, "registry") for name, path in _registry_browsers())
    raw.extend((name, path, "common") for name, path in _common_browser_paths())

    for exe, name in (
        ("chrome.exe", "Google Chrome"),
        ("msedge.exe", "Microsoft Edge"),
        ("brave.exe", "Brave"),
        ("vivaldi.exe", "Vivaldi"),
        ("firefox.exe", "Mozilla Firefox"),
    ):
        found = shutil.which(exe)
        if found:
            raw.append((name, Path(found), "PATH"))

    seen: set[str] = set()
    browsers: list[BrowserInfo] = []
    for name, path, source in raw:
        try:
            path = path.expanduser()
            if not path.exists() or not path.is_file():
                continue
            resolved = str(path.resolve()).casefold()
        except Exception:
            resolved = str(path).casefold()
            if not path.exists():
                continue
        if resolved in seen:
            continue
        seen.add(resolved)
        engine, support = classify_browser_executable(path, name)
        browsers.append(BrowserInfo(name=name.strip() or path.stem, executable=path, engine=engine, support=support, source=source))

    support_rank = {"full": 0, "experimental": 1, "unsupported": 2}
    browsers.sort(key=lambda b: (support_rank.get(b.support, 9), b.name.casefold(), str(b.executable).casefold()))
    return browsers
