from __future__ import annotations

import tkinter as tk
from tkinter import ttk

from ..agent.facebook_service import FacebookService
from ..config import Settings
from ..storage.db import ChatDB
from . import theme
from .activity_view import ActivityView
from .advanced_view import AdvancedView
from .agent_picker import AgentPicker
from .chat_window import ChatWindow
from .resources import asset_path
from .settings_view import SettingsView


class App(tk.Tk):
    """ChatGPT-like compact desktop shell.

    The left sidebar owns navigation and recent conversations. Heavy components
    (local AI model and browser automation) remain lazy so the shell itself stays
    responsive on 4 GB machines.
    """

    def __init__(self):
        super().__init__()
        self.withdraw()
        self.title("Your Assistant Agent")
        self.geometry("1120x760")
        self.minsize(860, 620)
        self.configure(bg=theme.BG)

        self.settings_obj = Settings.load()
        if not self.settings_obj.selected_agent:
            self.settings_obj.selected_agent = "arabic"
        self.db = ChatDB()
        self.facebook = FacebookService(self.db, self.settings_obj)
        self.facebook.start_scheduler()

        self.current = None
        self.shell = None
        self.sidebar = None
        self.main = None
        self.main_header = None
        self.content = None
        self.sessions_frame = None
        self.chat_window: ChatWindow | None = None
        self.activity_view: ActivityView | None = None
        self.settings_view: SettingsView | None = None
        self.advanced_view: AdvancedView | None = None
        self.current_session_id: int | None = None
        self.current_view = "chat"
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
        style.configure("Accent.TButton", font=("Segoe UI", 10, "bold"), padding=(11, 7))
        style.configure("TButton", padding=(8, 6))
        style.configure("TLabelframe", background=theme.BG, bordercolor=theme.BORDER)
        style.configure("TLabelframe.Label", background=theme.BG, foreground=theme.TEXT, font=("Segoe UI", 10, "bold"))

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
        splash.configure(bg="#ffffff", highlightthickness=1, highlightbackground=theme.BORDER)
        width, height = 500, 390
        sw, sh = splash.winfo_screenwidth(), splash.winfo_screenheight()
        splash.geometry(f"{width}x{height}+{(sw-width)//2}+{(sh-height)//2}")
        try:
            logo = tk.PhotoImage(file=str(asset_path("brand_mark_256.png")))
            self._brand_images.append(logo)
            tk.Label(splash, image=logo, bg="#ffffff").pack(pady=(24, 4))
        except Exception:
            pass
        tk.Label(splash, text="Your Assistant Agent", bg="#ffffff", fg="#172554", font=("Segoe UI", 22, "bold")).pack(pady=(0, 6))
        tk.Label(splash, text="Chat • Smart Agent • Local AI", bg="#ffffff", fg=theme.MUTED, font=("Segoe UI", 10)).pack()
        self.update_idletasks()
        self.after(800, lambda: self._finish_splash(splash))

    def _finish_splash(self, splash: tk.Toplevel) -> None:
        try:
            splash.destroy()
        except Exception:
            pass
        if self.settings_obj.remember_agent and self.settings_obj.selected_agent in {"arabic", "general"}:
            self.show_main(self.settings_obj.selected_agent)
        else:
            self.show_picker()
        self.deiconify()
        self.lift()

    def _clear_root(self):
        if self.chat_window:
            try:
                self.chat_window.shutdown()
            except Exception:
                pass
        self.chat_window = None
        self.activity_view = None
        self.settings_view = None
        self.advanced_view = None
        self.shell = self.sidebar = self.main = self.main_header = self.content = self.sessions_frame = None
        for child in self.winfo_children():
            if isinstance(child, tk.Toplevel):
                continue
            child.destroy()

    def show_picker(self):
        self._clear_root()
        self.current = AgentPicker(self, self._selected, self.settings_obj.remember_agent)
        self.current.pack(fill="both", expand=True)

    def _selected(self, key: str, remember: bool):
        self.settings_obj.selected_agent = key
        self.settings_obj.remember_agent = remember
        self.settings_obj.save()
        self.facebook.update_settings(self.settings_obj)
        self.db.add_activity("agent_selected", key)
        self.show_main(key)

    # ---------------- Main shell ----------------
    def show_main(self, key: str, session_id: int | None = None):
        self._clear_root()
        self.current = None
        self.settings_obj.selected_agent = key
        self.settings_obj.save()
        self.facebook.update_settings(self.settings_obj)

        shell = tk.Frame(self, bg=theme.BG)
        shell.pack(fill="both", expand=True)
        shell.grid_columnconfigure(1, weight=1)
        shell.grid_rowconfigure(0, weight=1)
        self.shell = shell

        self.sidebar = tk.Frame(shell, bg=theme.SIDEBAR, width=242)
        self.sidebar.grid(row=0, column=0, sticky="nsw")
        self.sidebar.grid_propagate(False)
        self.main = tk.Frame(shell, bg=theme.BG)
        self.main.grid(row=0, column=1, sticky="nsew")
        self.main.grid_rowconfigure(1, weight=1)
        self.main.grid_columnconfigure(0, weight=1)

        self._build_sidebar()
        self._build_header()

        self.content = tk.Frame(self.main, bg=theme.BG)
        self.content.grid(row=1, column=0, sticky="nsew")
        self.content.grid_rowconfigure(0, weight=1)
        self.content.grid_columnconfigure(0, weight=1)

        if session_id is None:
            sessions = self.db.list_sessions(1)
            if sessions:
                session_id = int(sessions[0]["id"])
            else:
                session_id = self.db.create_session(key)
        self.show_chat_session(int(session_id))

    def _build_sidebar(self):
        sb = self.sidebar
        if not sb:
            return
        top = tk.Frame(sb, bg=theme.SIDEBAR)
        top.pack(fill="x", padx=12, pady=(14, 8))
        try:
            logo = tk.PhotoImage(file=str(asset_path("brand_mark_64.png")))
            self._brand_images.append(logo)
            tk.Label(top, image=logo, bg=theme.SIDEBAR).pack(side="left")
        except Exception:
            pass
        tk.Label(top, text="Your Assistant\nAgent", bg=theme.SIDEBAR, fg=theme.TEXT, font=("Segoe UI", 11, "bold"), justify="left").pack(side="left", padx=7)

        self._side_button(sb, "＋  محادثة جديدة", self.new_chat, strong=True).pack(fill="x", padx=12, pady=(6, 10))

        tk.Label(sb, text="المحادثات", bg=theme.SIDEBAR, fg=theme.MUTED, font=("Segoe UI", 9, "bold"), anchor="w").pack(fill="x", padx=16, pady=(4, 4))
        self.sessions_frame = tk.Frame(sb, bg=theme.SIDEBAR)
        self.sessions_frame.pack(fill="both", expand=True, padx=8)
        self._refresh_sessions()

        bottom = tk.Frame(sb, bg=theme.SIDEBAR)
        bottom.pack(fill="x", side="bottom", padx=8, pady=10)
        self._side_button(bottom, "💬  المحادثة", lambda: self.navigate("chat")).pack(fill="x", pady=2)
        self._side_button(bottom, "◷  النشاط", lambda: self.navigate("activity")).pack(fill="x", pady=2)
        self._side_button(bottom, "⚙  الإعدادات", lambda: self.navigate("settings")).pack(fill="x", pady=2)
        self._side_button(bottom, "⋯  متقدم", lambda: self.navigate("advanced")).pack(fill="x", pady=2)
        self._side_button(bottom, "⇄  تغيير الوكيل", self.show_picker).pack(fill="x", pady=(8, 2))

    def _side_button(self, parent, text: str, command, strong: bool = False):
        bg = "#ffffff" if strong else theme.SIDEBAR
        return tk.Button(
            parent,
            text=text,
            command=command,
            anchor="w",
            relief="flat",
            bd=0,
            bg=bg,
            activebackground=theme.SIDEBAR_HOVER,
            fg=theme.TEXT,
            font=("Segoe UI", 10, "bold" if strong else "normal"),
            padx=10,
            pady=9,
            cursor="hand2",
        )

    def _refresh_sessions(self):
        if not self.sessions_frame:
            return
        for w in self.sessions_frame.winfo_children():
            w.destroy()
        for s in self.db.list_sessions(10):
            sid = int(s["id"])
            title = str(s["title"] or "محادثة جديدة")
            if len(title) > 28:
                title = title[:27] + "…"
            active = sid == self.current_session_id and self.current_view == "chat"
            btn = tk.Button(
                self.sessions_frame,
                text=title,
                command=lambda x=sid: self.show_chat_session(x),
                anchor="w",
                relief="flat",
                bd=0,
                bg=theme.SIDEBAR_ACTIVE if active else theme.SIDEBAR,
                activebackground=theme.SIDEBAR_HOVER,
                fg=theme.TEXT,
                font=("Segoe UI", 9),
                padx=8,
                pady=7,
                cursor="hand2",
            )
            btn.pack(fill="x", pady=1)

    def _build_header(self):
        if not self.main:
            return
        header = tk.Frame(self.main, bg=theme.PANEL, height=58, highlightbackground=theme.BORDER, highlightthickness=0)
        header.grid(row=0, column=0, sticky="ew")
        header.grid_propagate(False)
        header.grid_columnconfigure(0, weight=1)
        self.main_header = header
        self.header_title = tk.Label(header, text="المحادثة", bg=theme.PANEL, fg=theme.TEXT, font=("Segoe UI", 12, "bold"))
        self.header_title.grid(row=0, column=0, sticky="w", padx=20, pady=17)
        self.header_agent = tk.Label(
            header,
            text="",
            bg="#eef2ff",
            fg=theme.ACCENT,
            font=("Segoe UI", 9, "bold"),
            padx=9,
            pady=5,
        )
        self.header_agent.grid(row=0, column=1, padx=6)
        self.header_smart = tk.Label(
            header,
            text="Smart Agent ON" if self.settings_obj.smart_agent_enabled else "Smart Agent OFF",
            bg="#ecfdf3" if self.settings_obj.smart_agent_enabled else "#f3f4f6",
            fg="#087f5b" if self.settings_obj.smart_agent_enabled else theme.MUTED,
            font=("Segoe UI", 9, "bold"),
            padx=9,
            pady=5,
        )
        self.header_smart.grid(row=0, column=2, padx=6)
        self.stop_ai_btn = tk.Button(
            header, text="إيقاف AI", command=self._stop_ai_from_header, relief="flat", bd=0,
            bg=theme.PANEL, activebackground=theme.SIDEBAR_HOVER, fg=theme.MUTED,
            font=("Segoe UI", 9), padx=8, pady=5, cursor="hand2"
        )
        self.stop_ai_btn.grid(row=0, column=3, padx=(0, 18))
        self._update_header_agent()

    def _stop_ai_from_header(self):
        if self.chat_window:
            self.chat_window.stop_ai()

    def _update_header_agent(self):
        if hasattr(self, "header_agent"):
            label = "Arabic Agent" if self.settings_obj.selected_agent == "arabic" else "General Agent"
            self.header_agent.config(text=label)
        if hasattr(self, "header_smart"):
            enabled = self.settings_obj.smart_agent_enabled
            self.header_smart.config(
                text="Smart Agent ON" if enabled else "Smart Agent OFF",
                bg="#ecfdf3" if enabled else "#f3f4f6",
                fg="#087f5b" if enabled else theme.MUTED,
            )

    def _clear_content(self):
        if self.chat_window:
            try:
                self.chat_window.shutdown()
            except Exception:
                pass
        self.chat_window = None
        self.activity_view = None
        self.settings_view = None
        self.advanced_view = None
        if self.content:
            for child in self.content.winfo_children():
                child.destroy()

    def navigate(self, view: str):
        if view == "chat":
            if self.current_session_id:
                self.show_chat_session(self.current_session_id)
            else:
                self.new_chat()
            return
        self.current_view = view
        self._clear_content()
        self._refresh_sessions()
        titles = {"activity": "النشاط", "settings": "الإعدادات", "advanced": "متقدم"}
        self.header_title.config(text=titles.get(view, view))
        if view == "activity":
            self.activity_view = ActivityView(self.content)
            self.activity_view.grid(row=0, column=0, sticky="nsew")
        elif view == "settings":
            self.settings_view = SettingsView(self.content, self.settings_obj, self._settings_saved)
            self.settings_view.grid(row=0, column=0, sticky="nsew")
        elif view == "advanced":
            self.advanced_view = AdvancedView(self.content, self.facebook, self.settings_obj, on_activity=self._refresh_activity)
            self.advanced_view.grid(row=0, column=0, sticky="nsew")

    def new_chat(self):
        sid = self.db.create_session(self.settings_obj.selected_agent or "arabic")
        self.show_chat_session(sid)

    def show_chat_session(self, session_id: int):
        session = self.db.get_session(session_id)
        if not session:
            session_id = self.db.create_session(self.settings_obj.selected_agent or "arabic")
            session = self.db.get_session(session_id)
        agent_key = str((session or {}).get("agent") or self.settings_obj.selected_agent or "arabic")
        self.current_session_id = int(session_id)
        self.current_view = "chat"
        self._clear_content()
        self.header_title.config(text="المحادثة")
        self._refresh_sessions()
        self.chat_window = ChatWindow(
            self.content,
            agent_key,
            self.settings_obj,
            self.current_session_id,
            self.facebook,
            on_activity=self._refresh_activity,
            on_session_title_changed=self._refresh_sessions,
        )
        self.chat_window.grid(row=0, column=0, sticky="nsew")

    def _settings_saved(self, settings: Settings):
        previous_key = self.settings_obj.selected_agent
        self.settings_obj = settings
        self.facebook.update_settings(settings)
        self.db.add_activity(
            "settings_saved",
            f"agent={settings.selected_agent}; smart={settings.smart_agent_enabled}; ctx={settings.context_tokens}; threads={settings.threads}",
        )
        self._update_header_agent()
        if settings.selected_agent != previous_key:
            self.new_chat()
            return
        if self.chat_window:
            self.chat_window.apply_settings(settings)
        self._refresh_activity()

    def _refresh_activity(self):
        if self.activity_view:
            self.activity_view.refresh()
        if self.advanced_view:
            self.advanced_view.refresh()

    def _close(self):
        if self.chat_window:
            try:
                self.chat_window.shutdown()
            except Exception:
                pass
        try:
            self.facebook.shutdown()
        except Exception:
            pass
        self.destroy()
