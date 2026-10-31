from __future__ import annotations

import threading
from pathlib import Path

from .resources import asset_path


class TrayController:
    """Tiny optional pystray wrapper. Imported only when the window is hidden."""

    def __init__(self, root, on_open, on_exit):
        self.root = root
        self.on_open = on_open
        self.on_exit = on_exit
        self.icon = None
        self.thread = None

    def start(self):
        if self.icon is not None:
            return
        import pystray
        from PIL import Image

        image = Image.open(Path(asset_path("brand_mark_64.png"))).convert("RGBA")
        menu = pystray.Menu(
            pystray.MenuItem("Open Your Assistant Agent", lambda *_: self.on_open(), default=True),
            pystray.MenuItem("Exit", lambda *_: self._exit()),
        )
        self.icon = pystray.Icon("YourAssistantAgent", image, "Your Assistant Agent", menu)
        self.thread = threading.Thread(target=self.icon.run, daemon=True, name="yaa-system-tray")
        self.thread.start()

    def _exit(self):
        try:
            if self.icon:
                self.icon.stop()
        finally:
            self.root.after(0, self.on_exit)

    def stop(self):
        if self.icon:
            self.icon.stop()
            self.icon = None
