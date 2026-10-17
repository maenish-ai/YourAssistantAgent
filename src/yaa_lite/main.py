from __future__ import annotations

import ctypes
import os
import sys
import threading
import tkinter as tk


def _set_windows_app_id() -> None:
    if os.name != "nt":
        return
    try:
        ctypes.windll.shell32.SetCurrentProcessExplicitAppUserModelID(
            "YourAssistantAgent.Desktop.2.1.0"
        )
    except Exception:
        pass


def _self_test() -> int:
    """Fast packaged-startup check used by CI before publishing the installer."""
    from .ui.app import App  # noqa: F401
    from .ui.resources import asset_path
    from .agent.orchestrator import SmartAgentController  # noqa: F401
    from .agent.tools import ToolRegistry  # noqa: F401
    from .agent.hammer_agent import HammerAgentRouter, PRIMARY_MODEL_LABEL  # noqa: F401
    from .security.manager import SecurityManager  # noqa: F401
    from .backup.service import BackupService  # noqa: F401
    from .browser_bridge.server import BrowserBridge  # noqa: F401
    from .voice.service import VoiceService  # noqa: F401

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


def _replace_visible_hammer_labels(widget) -> None:
    """Upgrade old shell labels without duplicating the large App class."""
    try:
        text = widget.cget("text")
        if isinstance(text, str) and text.strip() == "Hammer":
            widget.configure(text="Qwen")
        elif isinstance(text, str) and text.strip() == "Hammer 2.1":
            widget.configure(text="Qwen3 1.7B")
    except Exception:
        pass
    try:
        for child in widget.winfo_children():
            _replace_visible_hammer_labels(child)
    except Exception:
        pass


def main() -> int:
    _set_windows_app_id()
    if "--self-test" in sys.argv:
        return _self_test()

    from .ui.app import App
    from .voice.service import VoiceService

    class QwenApp(App):
        def _build_header(self):
            super()._build_header()
            try:
                self.header_agent.config(text="Qwen3 1.7B")
            except Exception:
                pass

        def _build_sidebar(self):
            super()._build_sidebar()
            _replace_visible_hammer_labels(self.sidebar)

        def _voice_request(self, chat):
            # Pressing the microphone is explicit user intent; do not require a
            # separate enable toggle before the first voice conversation.
            try:
                svc = VoiceService(self.settings_obj)
            except Exception as exc:
                chat.voice_failed(str(exc))
                return

            def work():
                try:
                    text = svc.listen_once()
                except Exception as exc:
                    self.after(0, lambda: chat.voice_failed(str(exc)))
                    return
                if text:
                    self.after(0, lambda: chat.prefill_and_send(text))

            threading.Thread(target=work, daemon=True, name="yaa-voice-listen").start()

    app = QwenApp()
    app.mainloop()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
