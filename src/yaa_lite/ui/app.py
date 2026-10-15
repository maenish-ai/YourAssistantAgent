from __future__ import annotations
import tkinter as tk
from tkinter import ttk

from ..config import Settings
from .agent_picker import AgentPicker
from .chat_window import ChatWindow
from . import theme

class App(tk.Tk):
    def __init__(self):
        super().__init__()
        self.title("Your Assistant Agent")
        self.geometry("900x680")
        self.minsize(720, 560)
        self.configure(bg=theme.BG)
        self.settings_obj = Settings.load()
        self.current = None
        self._styles()
        self.protocol("WM_DELETE_WINDOW", self._close)
        if self.settings_obj.remember_agent and self.settings_obj.selected_agent in {"arabic", "general"}:
            self.show_chat(self.settings_obj.selected_agent)
        else:
            self.show_picker()

    def _styles(self):
        style = ttk.Style(self)
        try:
            style.theme_use("clam")
        except tk.TclError:
            pass
        style.configure("TFrame", background=theme.BG)
        style.configure("Card.TFrame", background=theme.PANEL, relief="solid", borderwidth=1)
        style.configure("TLabel", background=theme.BG, foreground=theme.TEXT, font=("Segoe UI", 10))
        style.configure("Title.TLabel", font=("Segoe UI", 22, "bold"), foreground=theme.TEXT)
        style.configure("CardTitle.TLabel", font=("Segoe UI", 12, "bold"), foreground=theme.TEXT)
        style.configure("Muted.TLabel", foreground=theme.MUTED)
        style.configure("Accent.TButton", font=("Segoe UI", 10, "bold"))

    def _swap(self, frame):
        if self.current:
            if hasattr(self.current, "shutdown"):
                try: self.current.shutdown()
                except Exception: pass
            self.current.destroy()
        self.current = frame
        self.current.pack(fill="both", expand=True)

    def show_picker(self):
        self._swap(AgentPicker(self, self._selected, self.settings_obj.remember_agent))

    def _selected(self, key: str, remember: bool):
        self.settings_obj.selected_agent = key
        self.settings_obj.remember_agent = remember
        self.settings_obj.save()
        self.show_chat(key)

    def show_chat(self, key: str):
        self._swap(ChatWindow(self, key, self.settings_obj, self.show_picker))

    def _close(self):
        if self.current and hasattr(self.current, "shutdown"):
            try: self.current.shutdown()
            except Exception: pass
        self.destroy()
