from __future__ import annotations

import tkinter as tk
from tkinter import ttk

from ..config import Settings
from .agent_picker import AgentPicker
from .chat_window import ChatWindow
from .resources import asset_path
from . import theme


class App(tk.Tk):
    def __init__(self):
        super().__init__()
        self.withdraw()
        self.title("Your Assistant Agent")
        self.geometry("900x680")
        self.minsize(720, 560)
        self.configure(bg=theme.BG)
        self.settings_obj = Settings.load()
        self.current = None
        self._brand_images: list[tk.PhotoImage] = []
        self._styles()
        self._apply_brand_icon()
        self.protocol("WM_DELETE_WINDOW", self._close)
        self._show_splash()

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

    def _apply_brand_icon(self) -> None:
        try:
            icon = tk.PhotoImage(file=str(asset_path("brand_mark_64.png")))
            self._brand_images.append(icon)
            self.iconphoto(True, icon)
        except Exception:
            pass
        try:
            self.iconbitmap(default=str(asset_path("icon.ico")))
        except Exception:
            pass

    def _show_splash(self) -> None:
        splash = tk.Toplevel(self)
        splash.overrideredirect(True)
        splash.configure(bg="#ffffff", highlightthickness=1, highlightbackground="#e4e7ec")
        width, height = 500, 390
        sw, sh = splash.winfo_screenwidth(), splash.winfo_screenheight()
        splash.geometry(f"{width}x{height}+{(sw-width)//2}+{(sh-height)//2}")
        try:
            logo = tk.PhotoImage(file=str(asset_path("brand_mark_256.png")))
            self._brand_images.append(logo)
            tk.Label(splash, image=logo, bg="#ffffff").pack(pady=(24, 4))
        except Exception:
            pass
        tk.Label(
            splash,
            text="Your Assistant Agent",
            bg="#ffffff",
            fg="#172554",
            font=("Segoe UI", 22, "bold"),
        ).pack(pady=(0, 6))
        tk.Label(
            splash,
            text="Local AI • Lightweight • Private",
            bg="#ffffff",
            fg="#667085",
            font=("Segoe UI", 10),
        ).pack()
        self.update_idletasks()
        self.after(900, lambda: self._finish_splash(splash))

    def _finish_splash(self, splash: tk.Toplevel) -> None:
        try:
            splash.destroy()
        except Exception:
            pass
        if self.settings_obj.remember_agent and self.settings_obj.selected_agent in {"arabic", "general"}:
            self.show_chat(self.settings_obj.selected_agent)
        else:
            self.show_picker()
        self.deiconify()
        self.lift()

    def _swap(self, frame):
        if self.current:
            if hasattr(self.current, "shutdown"):
                try:
                    self.current.shutdown()
                except Exception:
                    pass
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
            try:
                self.current.shutdown()
            except Exception:
                pass
        self.destroy()
