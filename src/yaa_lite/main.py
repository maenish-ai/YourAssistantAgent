from __future__ import annotations

import ctypes
import os
import sys


def _set_windows_app_id() -> None:
    if os.name != "nt":
        return
    try:
        ctypes.windll.shell32.SetCurrentProcessExplicitAppUserModelID(
            "YourAssistantAgent.Desktop.1.6.0"
        )
    except Exception:
        pass


def _self_test() -> int:
    """Fast packaged-startup check used by CI before publishing the installer."""
    from .ui.app import App  # noqa: F401 - import itself is the important test
    from .ui.resources import asset_path
    from .agent.orchestrator import SmartAgentController  # noqa: F401
    from .agent.tools import ToolRegistry  # noqa: F401

    required = (
        "icon.ico",
        "brand_mark_64.png",
        "brand_mark_128.png",
        "brand_mark_256.png",
    )
    missing = [name for name in required if not asset_path(name).exists()]
    if missing:
        raise RuntimeError("Missing branding assets: " + ", ".join(missing))
    return 0


def main() -> int:
    _set_windows_app_id()
    if "--self-test" in sys.argv:
        return _self_test()

    from .ui.app import App

    app = App()
    app.mainloop()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
