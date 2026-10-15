from __future__ import annotations

import tkinter as tk
from tkinter import ttk

from ..agent.facebook_service import FacebookService
from ..agent.hammer_agent import HAMMER_MODEL_LABEL
from ..config import Settings
from ..storage.db import ChatDB
from . import theme
from .activity_view import ActivityView, FRIENDLY
from .advanced_view import AdvancedView
from .chat_window import ChatWindow
from .i18n import ui_text
from .resources import asset_path
from .settings_view import SettingsView


class App(tk.Tk):
    """Compact ChatGPT-like shell with one visible Smart Agent."""

    def __init__(self):
        super().__init__()
        self.withdraw()
        self.title("Your Assistant Agent")
        self.geometry("1160x780")
        self.minsize(900, 640)
        self.configure(bg=theme.BG)

        self.settings_obj = Settings.load()
        self.settings_obj.selected_agent = "hammer"
        self.db = ChatDB()
        self.facebook = FacebookService(self.db, self.settings_obj)
        self.facebook.start_scheduler()

        self.shell = self.sidebar = self.main = self.main_header = self.content = self.sessions_frame = None
        self.chat_window: ChatWindow | None = None
        self.activity_view: ActivityView | None = None
        self.settings_view: SettingsView | None = None
        self.advanced_view: AdvancedView | None = None
        self.current_session_id: int | None = None
        self.current_view = "chat"
        self._brand_images: list[tk.PhotoImage] = []
        self.live_status_label = None

        self._styles()
        self._apply_brand_icon()
        self.protocol("WM_DELETE_WINDOW", self._close)
        self._show_splash()

    def t(self, ar: str, en: str) -> str:
        return ui_text(ar, en, self.settings_obj.interface_language)

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
        tk.Label(splash, text="Hammer 2.1 • Smart Agent • Local & Private", bg="#ffffff", fg=theme.MUTED, font=("Segoe UI", 10)).pack()
        self.update_idletasks()
        self.after(800, lambda: self._finish_splash(splash))

    def _finish_splash(self, splash: tk.Toplevel) -> None:
        try:
            splash.destroy()
        except Exception:
            pass
        self.show_main()
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

    def show_main(self, session_id: int | None = None):
        self._clear_root()
        self.settings_obj.selected_agent = "hammer"
        self.settings_obj.remember_agent = True
        self.settings_obj.save()
        self.facebook.update_settings(self.settings_obj)

        shell = tk.Frame(self, bg=theme.BG)
        shell.pack(fill="both", expand=True)
        shell.grid_columnconfigure(1, weight=1)
        shell.grid_rowconfigure(0, weight=1)
        self.shell = shell

        self.sidebar = tk.Frame(shell, bg=theme.SIDEBAR, width=258)
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
            session_id = int(sessions[0]["id"]) if sessions else self.db.create_session("hammer")
        self.show_chat_session(int(session_id))
        self.after(900, self._poll_sidebar_status)

    def _build_sidebar(self):
        sb = self.sidebar
        top = tk.Frame(sb, bg=theme.SIDEBAR)
        top.pack(fill="x", padx=12, pady=(14, 8))
        try:
            logo = tk.PhotoImage(file=str(asset_path("brand_mark_64.png")))
            self._brand_images.append(logo)
            tk.Label(top, image=logo, bg=theme.SIDEBAR).pack(side="left")
        except Exception:
            pass
        tk.Label(top, text="Your Assistant\nAgent", bg=theme.SIDEBAR, fg=theme.TEXT, font=("Segoe UI", 11, "bold"), justify="left").pack(side="left", padx=7)

        self._side_button(sb, self.t("＋  محادثة جديدة", "＋  New chat"), self.new_chat, strong=True).pack(fill="x", padx=12, pady=(6, 10))
        tk.Label(sb, text=self.t("المحادثات", "Chats"), bg=theme.SIDEBAR, fg=theme.MUTED, font=("Segoe UI", 9, "bold"), anchor="w").pack(fill="x", padx=16, pady=(4, 4))
        self.sessions_frame = tk.Frame(sb, bg=theme.SIDEBAR)
        self.sessions_frame.pack(fill="both", expand=True, padx=8)
        self._refresh_sessions()

        bottom = tk.Frame(sb, bg=theme.SIDEBAR)
        bottom.pack(fill="x", side="bottom", padx=8, pady=10)
        self.live_status_label = tk.Label(
            bottom,
            text=self.t("● جاهز", "● Ready"),
            bg=theme.SIDEBAR,
            fg="#087f5b",
            anchor="w",
            justify="left",
            wraplength=220,
            font=("Segoe UI", 8),
            padx=10,
            pady=6,
        )
        self.live_status_label.pack(fill="x", pady=(0, 4))
        self._side_button(bottom, self.t("💬  المحادثة", "💬  Chat"), lambda: self.navigate("chat")).pack(fill="x", pady=2)
        self._side_button(bottom, self.t("◉  الحالة", "◉  Status"), lambda: self.navigate("status")).pack(fill="x", pady=2)
        self._side_button(bottom, self.t("⚙  الإعدادات", "⚙  Settings"), lambda: self.navigate("settings")).pack(fill="x", pady=2)
        self._side_button(bottom, self.t("⋯  متقدم", "⋯  Advanced"), lambda: self.navigate("advanced")).pack(fill="x", pady=2)

    def _side_button(self, parent, text: str, command, strong: bool = False):
        bg = "#ffffff" if strong else theme.SIDEBAR
        return tk.Button(parent, text=text, command=command, anchor="w", relief="flat", bd=0, bg=bg,
                         activebackground=theme.SIDEBAR_HOVER, fg=theme.TEXT,
                         font=("Segoe UI", 10, "bold" if strong else "normal"), padx=10, pady=9, cursor="hand2")

    def _refresh_sessions(self):
        if not self.sessions_frame:
            return
        for w in self.sessions_frame.winfo_children():
            w.destroy()
        for s in self.db.list_sessions(10):
            sid = int(s["id"])
            title = str(s["title"] or self.t("محادثة جديدة", "New chat"))
            if len(title) > 30:
                title = title[:29] + "…"
            active = sid == self.current_session_id and self.current_view == "chat"
            btn = tk.Button(self.sessions_frame, text=title, command=lambda x=sid: self.show_chat_session(x), anchor="w",
                            relief="flat", bd=0, bg=theme.SIDEBAR_ACTIVE if active else theme.SIDEBAR,
                            activebackground=theme.SIDEBAR_HOVER, fg=theme.TEXT, font=("Segoe UI", 9), padx=8, pady=7, cursor="hand2")
            btn.pack(fill="x", pady=1)

    def _build_header(self):
        header = tk.Frame(self.main, bg=theme.PANEL, height=60)
        header.grid(row=0, column=0, sticky="ew")
        header.grid_propagate(False)
        header.grid_columnconfigure(0, weight=1)
        self.main_header = header
        self.header_title = tk.Label(header, text=self.t("المحادثة", "Chat"), bg=theme.PANEL, fg=theme.TEXT, font=("Segoe UI", 12, "bold"))
        self.header_title.grid(row=0, column=0, sticky="w", padx=20, pady=17)
        self.header_agent = tk.Label(header, text="Hammer 2.1", bg="#eef2ff", fg=theme.ACCENT, font=("Segoe UI", 9, "bold"), padx=9, pady=5)
        self.header_agent.grid(row=0, column=1, padx=6)
        self.header_smart = tk.Label(header, text=self.t("الوكيل الذكي مفعّل", "Smart Agent ON") if self.settings_obj.smart_agent_enabled else self.t("الوكيل الذكي متوقف", "Smart Agent OFF"),
                                     bg="#ecfdf3" if self.settings_obj.smart_agent_enabled else "#f3f4f6",
                                     fg="#087f5b" if self.settings_obj.smart_agent_enabled else theme.MUTED,
                                     font=("Segoe UI", 9, "bold"), padx=9, pady=5)
        self.header_smart.grid(row=0, column=2, padx=6)
        self.stop_ai_btn = tk.Button(header, text=self.t("إيقاف AI", "Stop AI"), command=self._stop_ai_from_header,
                                     relief="flat", bd=0, bg=theme.PANEL, activebackground=theme.SIDEBAR_HOVER,
                                     fg=theme.MUTED, font=("Segoe UI", 9), padx=8, pady=5, cursor="hand2")
        self.stop_ai_btn.grid(row=0, column=3, padx=(0, 18))

    def _stop_ai_from_header(self):
        if self.chat_window:
            self.chat_window.stop_ai()

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
        titles = {"status": self.t("الحالة", "Status"), "settings": self.t("الإعدادات", "Settings"), "advanced": self.t("متقدم", "Advanced")}
        self.header_title.config(text=titles.get(view, view))
        if view == "status":
            self.activity_view = ActivityView(self.content, self.facebook, self.settings_obj)
            self.activity_view.grid(row=0, column=0, sticky="nsew")
        elif view == "settings":
            self.settings_view = SettingsView(self.content, self.settings_obj, self._settings_saved)
            self.settings_view.grid(row=0, column=0, sticky="nsew")
        elif view == "advanced":
            self.advanced_view = AdvancedView(self.content, self.facebook, self.settings_obj, on_activity=self._refresh_activity)
            self.advanced_view.grid(row=0, column=0, sticky="nsew")

    def new_chat(self):
        sid = self.db.create_session("hammer")
        self.show_chat_session(sid)

    def show_chat_session(self, session_id: int):
        session = self.db.get_session(session_id)
        if not session:
            session_id = self.db.create_session("hammer")
        self.current_session_id = int(session_id)
        self.current_view = "chat"
        self._clear_content()
        self.header_title.config(text=self.t("المحادثة", "Chat"))
        self._refresh_sessions()
        self.chat_window = ChatWindow(self.content, "hammer", self.settings_obj, self.current_session_id, self.facebook,
                                      on_activity=self._refresh_activity, on_session_title_changed=self._refresh_sessions)
        self.chat_window.grid(row=0, column=0, sticky="nsew")

    def _settings_saved(self, settings: Settings):
        old_lang = self.settings_obj.interface_language
        self.settings_obj = settings
        self.facebook.update_settings(settings)
        self.db.add_activity("settings_saved", f"smart={settings.smart_agent_enabled}; language={settings.interface_language}; ctx={settings.context_tokens}; threads={settings.threads}")
        if settings.interface_language != old_lang:
            self.show_main(self.current_session_id)
            return
        if self.chat_window:
            self.chat_window.apply_settings(settings)
        if self.header_smart:
            self.header_smart.config(text=self.t("الوكيل الذكي مفعّل", "Smart Agent ON") if settings.smart_agent_enabled else self.t("الوكيل الذكي متوقف", "Smart Agent OFF"),
                                     bg="#ecfdf3" if settings.smart_agent_enabled else "#f3f4f6",
                                     fg="#087f5b" if settings.smart_agent_enabled else theme.MUTED)
        self._refresh_activity()

    def _refresh_activity(self):
        if self.activity_view:
            self.activity_view.refresh()
        if self.advanced_view:
            self.advanced_view.refresh()
        self._update_sidebar_status()

    def _update_sidebar_status(self):
        if not self.live_status_label:
            return
        rows = self.db.recent_activity(1)
        if not rows:
            self.live_status_label.config(text=self.t("● جاهز", "● Ready"), fg="#087f5b")
            return
        row = rows[0]
        icon, ar, en = FRIENDLY.get(row["kind"], ("•", row["kind"], row["kind"]))
        state = ui_text(ar, en, self.settings_obj.interface_language)
        detail = str(row.get("detail") or "")[:90]
        self.live_status_label.config(text=f"{icon} {state}\n{detail}", fg="#087f5b" if "error" not in row["kind"] else "#b42318")

    def _poll_sidebar_status(self):
        if not self.winfo_exists():
            return
        self._update_sidebar_status()
        self.after(900, self._poll_sidebar_status)

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
