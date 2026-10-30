"""GroqCloud-first desktop entrypoint; no periodic label sweeps or audio playback."""
from __future__ import annotations

import ctypes
import os
import sys


def _set_windows_app_id() -> None:
    if os.name == 'nt':
        try:
            ctypes.windll.shell32.SetCurrentProcessExplicitAppUserModelID('YourAssistantAgent.Desktop.3.0.0')
        except Exception:
            pass


def _self_test() -> int:
    """Lightweight packaged startup check; no window, credentials or network."""
    from .ui.app import App  # noqa: F401
    from .ui.resources import asset_path
    from .agent.orchestrator import SmartAgentController  # noqa: F401
    from .agent.tools import ToolRegistry  # noqa: F401
    from .security.manager import SecurityManager  # noqa: F401
    from .browser_bridge.server import BrowserBridge  # noqa: F401
    from .ai.runtime import GROQ_MODEL  # noqa: F401
    if os.name == 'nt':
        # Verify the UI Automation dependency in source and frozen Windows
        # builds without capturing the desktop or injecting any input.
        from pywinauto import Desktop  # noqa: F401
    from .text_first_v300 import is_single_facebook_link  # noqa: F401
    missing = [n for n in ('icon.ico', 'brand_mark_64.png', 'brand_mark_128.png', 'brand_mark_256.png')
               if not asset_path(n).exists()]
    if missing:
        raise RuntimeError('Missing branding assets: ' + ', '.join(missing))
    return 0


def _upgrade_old_visible_labels(widget) -> None:
    """One-shot text normalization; NEVER repeatedly scan the entire UI."""
    try:
        old = widget.cget('text')
        if isinstance(old, str) and old:
            new = old.replace('Qwen3 1.7B', 'GroqCloud • GPT-OSS 120B')
            new = new.replace('Qwen3', 'GroqCloud').replace('Qwen', 'GroqCloud')
            new = new.replace('Hammer 2.1', 'GroqCloud • GPT-OSS 120B')
            if new != old:
                widget.configure(text=new)
    except Exception:
        pass
    try:
        for child in widget.winfo_children():
            _upgrade_old_visible_labels(child)
    except Exception:
        pass


def main() -> int:
    from .bootstrap import configure_application
    configure_application()
    _set_windows_app_id()
    if '--self-test' in sys.argv:
        return _self_test()
    from .ui.app import App

    class GroqApp(App):
        def _build_sidebar(self):
            super()._build_sidebar()
            _upgrade_old_visible_labels(self.sidebar)

        def navigate(self, view):
            result = super().navigate(view)
            # Run only on deliberate view navigation; no CPU-burning timer.
            _upgrade_old_visible_labels(getattr(self, '_view_widget', None))
            return result

        def _build_header(self):
            super()._build_header()
            try:
                self.header_agent.configure(text='GroqCloud • GPT-OSS 120B')
            except Exception:
                pass

    GroqApp().mainloop()
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
