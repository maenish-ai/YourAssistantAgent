from __future__ import annotations

import os
import threading
import tkinter as tk
from tkinter import messagebox, simpledialog, ttk

from ..agent.facebook_service import FacebookService
from ..ai.runtime import LocalAIRuntime
from ..backup.service import BackupService
from ..browser_bridge.server import BrowserBridge
from ..config import Settings
from .. import __version__
from ..security.manager import SecurityManager
from ..storage.db import ChatDB
from . import theme
from .activity_view import ActivityView
from .backup_view import BackupView
from .chat_window import ChatWindow
from .facebook_view import FacebookView
from .home_view import HomeView
from .i18n import ui_text
from .resources import asset_path
from .settings_view import SettingsView
from .setup_wizard import SetupWizard
from .tasks_view import TasksView
from .unlock_dialog import UnlockDialog


class App(tk.Tk):
    """Your Assistant Agent v2 shell.

    Hammer is the only AI brain. This class owns the long-lived services and
    presents them through a compact, ChatGPT-like desktop shell.
    """

    def __init__(self):
        super().__init__()
        self.withdraw()
        self.title("Your Assistant Agent · " + __version__)
        self.geometry("1240x820")
        self.minsize(980, 650)

        self.settings_obj = Settings.load()
        theme.apply(self.settings_obj.appearance)
        self.configure(bg=theme.BG)
        self.security = SecurityManager()

        self.db: ChatDB | None = None
        self.runtime: LocalAIRuntime | None = None
        self.facebook: FacebookService | None = None
        self.backup: BackupService | None = None
        self.browser_bridge: BrowserBridge | None = None
        self.tray = None
        self.remote_worker = None
        self._remote_status = self.t("اتصال الهاتف غير مفعّل", "Phone connection is disabled")

        self.shell = self.sidebar = self.main = self.main_header = self.content = None
        self.sessions_frame = None
        self.session_search_var: tk.StringVar | None = None
        self.chat_window: ChatWindow | None = None
        self.current_session_id: int | None = None
        self.current_view = "home"
        self._view_widget = None
        self._brand_images: list[tk.PhotoImage] = []
        self._sidebar_status_labels: dict[str, tk.Label] = {}
        self._poll_after_id = None
        self._idle_after_id = None
        self._backup_after_id = None
        self._backup_sync_running = False

        self._styles()
        self._apply_brand_icon()
        self.protocol("WM_DELETE_WINDOW", self._on_close_request)
        self._show_splash()

    def t(self, ar: str, en: str) -> str:
        return ui_text(ar, en, self.settings_obj.interface_language)

    # ---------- bootstrap ----------
    def _styles(self):
        style = ttk.Style(self)
        try:
            style.theme_use("clam")
        except tk.TclError:
            pass
        style.configure(".", background=theme.BG, foreground=theme.TEXT, font=("Segoe UI",10))
        style.configure("TFrame", background=theme.BG)
        style.configure("Card.TFrame", background=theme.PANEL, relief="flat", borderwidth=0)
        style.configure("TLabel", background=theme.BG, foreground=theme.TEXT)
        style.configure("Title.TLabel", font=("Segoe UI",24,"bold"))
        style.configure("CardTitle.TLabel", font=("Segoe UI",13,"bold"))
        style.configure("Muted.TLabel", foreground=theme.MUTED)
        style.configure("TButton", background=theme.PANEL, foreground=theme.TEXT, borderwidth=0,
                        focusthickness=2, focuscolor=theme.ACCENT, padding=(14,10), anchor="center")
        style.map("TButton", background=[("active",theme.SIDEBAR_HOVER),("pressed",theme.SIDEBAR_ACTIVE)],
                  foreground=[("disabled",theme.MUTED)])
        style.configure("Accent.TButton", background=theme.BUTTON, foreground="#ffffff", font=("Segoe UI",10,"bold"))
        style.map("Accent.TButton", background=[("disabled",theme.BORDER),("active",theme.ACCENT_HOVER)],
                  foreground=[("disabled",theme.MUTED)])
        style.configure("Nav.TButton", background=theme.BG, anchor="w", padding=(12,6))
        style.configure("ActiveNav.TButton", background=theme.SIDEBAR_ACTIVE, foreground=theme.ACCENT, anchor="w", padding=(12,6))
        style.configure("TEntry", fieldbackground=theme.INPUT, foreground=theme.TEXT, insertcolor=theme.TEXT,
                        bordercolor=theme.BORDER, lightcolor=theme.BORDER, darkcolor=theme.BORDER, padding=(10,9))
        style.map("TEntry", bordercolor=[("focus",theme.ACCENT)])
        style.configure("TCombobox", fieldbackground=theme.INPUT, foreground=theme.TEXT, arrowcolor=theme.MUTED, padding=(8,7))
        style.map("TCombobox", fieldbackground=[("readonly",theme.INPUT)], foreground=[("readonly",theme.TEXT)])
        style.configure("TCheckbutton", background=theme.BG, foreground=theme.TEXT, padding=(0,6))
        style.map("TCheckbutton", background=[("active",theme.BG)], indicatorcolor=[("selected",theme.ACCENT)])
        style.configure("TLabelframe", background=theme.BG, bordercolor=theme.BORDER, relief="flat", borderwidth=1)
        style.configure("TLabelframe.Label", background=theme.BG, foreground=theme.ACCENT, font=("Segoe UI",11,"bold"))
        style.configure("Treeview", rowheight=38, fieldbackground=theme.PANEL, background=theme.PANEL, foreground=theme.TEXT, borderwidth=0)
        style.map("Treeview", background=[("selected",theme.SIDEBAR_ACTIVE)], foreground=[("selected",theme.TEXT)])
        style.configure("Treeview.Heading", background=theme.BG, foreground=theme.MUTED, padding=8)
        style.configure("Vertical.TScrollbar", background=theme.BORDER, troughcolor=theme.BG, borderwidth=0, arrowsize=12)

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
        splash.configure(bg="#ffffff", highlightthickness=1, highlightbackground="#dbe0ea")
        width, height = 500, 380
        sw, sh = splash.winfo_screenwidth(), splash.winfo_screenheight()
        splash.geometry(f"{width}x{height}+{(sw-width)//2}+{(sh-height)//2}")
        try:
            logo = tk.PhotoImage(file=str(asset_path("brand_mark_256.png")))
            self._brand_images.append(logo)
            tk.Label(splash, image=logo, bg="#ffffff").pack(pady=(22, 3))
        except Exception:
            pass
        tk.Label(splash, text="Your Assistant Agent", bg="#ffffff", fg="#172554", font=("Segoe UI", 22, "bold")).pack(pady=(0, 6))
        tk.Label(splash, text="Your computer. Connected.", bg="#ffffff", fg="#667085", font=("Segoe UI", 10)).pack()
        self.after(600, lambda: self._finish_splash(splash))

    def _finish_splash(self, splash: tk.Toplevel) -> None:
        try:
            splash.destroy()
        except Exception:
            pass
        self.deiconify()
        self.lift()
        self.after(20, self._security_gate)

    def _security_gate(self) -> None:
        # Setup first, then unlock, then services. No app data/cloud secrets are
        # opened before the local security layer is ready.
        if not self.settings_obj.first_run_complete or not self.security.configured:
            SetupWizard(self, self.settings_obj, self.security, self._after_setup)
            return
        try:
            prompt = self.security.should_prompt()
        except Exception:
            prompt = True
        if prompt:
            UnlockDialog(self, self.security, self.settings_obj.interface_language, self._after_unlock)
        else:
            self._after_unlock()

    def _after_setup(self) -> None:
        self.settings_obj = Settings.load()
        theme.apply(self.settings_obj.appearance)
        self.configure(bg=theme.BG)
        self._styles()
        self._start_services_and_ui()

    def _after_unlock(self) -> None:
        self._start_services_and_ui()

    def _activity(self, kind: str, detail: str) -> None:
        if self.db:
            self.db.add_activity(kind, detail)

    def _start_services_and_ui(self) -> None:
        if self.db is None:
            self.db = ChatDB()
        if self.runtime is None:
            self.runtime = LocalAIRuntime(
                context_tokens=self.settings_obj.context_tokens,
                threads=self.settings_obj.threads,
                retry_count=self.settings_obj.hammer_retry_count,
                performance_mode=self.settings_obj.performance_mode,
            )
        if self.browser_bridge is None:
            self.browser_bridge = BrowserBridge(activity=self._activity)
            try:
                self.browser_bridge.start()
            except Exception as exc:
                self._activity("browser_bridge_error", f"{type(exc).__name__}: {exc}")
        if self.facebook is None:
            self.facebook = FacebookService(self.db, self.settings_obj, activity=self._activity, browser_bridge=self.browser_bridge)
            self.facebook.start_scheduler()
        if self.backup is None:
            self.backup = BackupService(self.settings_obj, self.security, activity=self._activity)

        self._restart_remote_worker()
        self.show_main()
        self._apply_startup_page()
        self._schedule_background_polls()
        if "--start-in-tray" in __import__("sys").argv and self.settings_obj.first_run_complete:
            self.after(80, self._start_hidden_in_tray)
        if self.settings_obj.facebook_auto_check:
            threading.Thread(target=self._background_facebook_check, daemon=True, name="yaa-facebook-autocheck").start()

    def _apply_startup_page(self) -> None:
        target = self.settings_obj.startup_page
        if target == "last":
            target = self.settings_obj.last_page or "home"
        if target not in {"home", "chat", "status", "facebook", "tasks", "backup", "settings"}:
            target = "home"
        self.navigate(target)

    def _start_hidden_in_tray(self):
        if self._ensure_tray():
            self.withdraw()

    def _background_facebook_check(self):
        if not self.facebook:
            return
        try:
            self.facebook.verify_session_background()
        except Exception as exc:
            self._activity("facebook_connection_error", f"{type(exc).__name__}: {exc}")

    # ---------- shell ----------
    def _clear_root(self):
        self.chat_window = None
        self._view_widget = None
        for child in list(self.winfo_children()):
            if isinstance(child, tk.Toplevel):
                continue
            child.destroy()
        self.shell = self.sidebar = self.main = self.main_header = self.content = self.sessions_frame = None

    def show_main(self, session_id: int | None = None):
        assert self.db and self.runtime and self.facebook and self.backup
        self._clear_root()
        self.settings_obj.selected_agent = "hammer"
        self.settings_obj.remember_agent = True
        self.settings_obj.save()
        self.facebook.update_settings(self.settings_obj)
        self.backup.update_settings(self.settings_obj)

        self.configure(bg=theme.BG)
        shell = tk.Frame(self, bg=theme.BG)
        shell.pack(fill="both", expand=True)
        shell.grid_columnconfigure(1, weight=1)
        shell.grid_rowconfigure(0, weight=1)
        self.shell = shell

        # The user explicitly wants the navigation rail on the left for both languages.
        self.sidebar = tk.Frame(shell, bg=theme.SIDEBAR, width=240)
        self.sidebar.grid(row=0, column=0, sticky="nsw")
        self.sidebar.grid_propagate(False)
        self.main = tk.Frame(shell, bg=theme.BG)
        self.main.grid(row=0, column=1, sticky="nsew")
        self.main.grid_rowconfigure(1, weight=1)
        self.main.grid_columnconfigure(0, weight=1)

        if session_id is not None:
            self.current_session_id = int(session_id)
        elif self.current_session_id is None:
            sessions = self.db.list_sessions(1)
            self.current_session_id = int(sessions[0]["id"]) if sessions else self.db.create_session("hammer")

        self._build_sidebar()
        self._build_header()
        self.content = tk.Frame(self.main, bg=theme.BG)
        self.content.grid(row=1, column=0, sticky="nsew")
        self.content.grid_rowconfigure(0, weight=1)
        self.content.grid_columnconfigure(0, weight=1)

    def _build_sidebar(self):
        sb = self.sidebar
        assert sb is not None
        top = tk.Frame(sb, bg=theme.SIDEBAR)
        top.pack(fill="x", padx=12, pady=(13, 8))
        try:
            logo = tk.PhotoImage(file=str(asset_path("brand_mark_64.png")))
            self._brand_images.append(logo)
            tk.Label(top, image=logo, bg=theme.SIDEBAR).pack(side="left")
        except Exception:
            pass
        tk.Label(top, text="Your Assistant\nAgent · " + __version__, bg=theme.SIDEBAR, fg=theme.TEXT,
                 font=("Segoe UI", 11, "bold"), justify="left").pack(side="left", padx=7)

        self._nav_button(sb, self.t("⌂  الرئيسية", "⌂  Home"), lambda: self.navigate("home"), "home").pack(fill="x", padx=10, pady=2)
        self._nav_button(sb, self.t("＋  محادثة جديدة", "＋  New chat"), self.new_chat, "new").pack(fill="x", padx=10, pady=(4, 6))

        search_row = tk.Frame(sb, bg=theme.SIDEBAR)
        search_row.pack(fill="x", padx=12, pady=(0, 5))
        self.session_search_var = tk.StringVar()
        ent = ttk.Entry(search_row, textvariable=self.session_search_var)
        ent.pack(fill="x")
        ent.insert(0, "")
        ent.bind("<KeyRelease>", lambda _e: self._refresh_sessions())

        tk.Label(sb, text=self.t("المحادثات", "Chats"), bg=theme.SIDEBAR, fg=theme.MUTED,
                 font=("Segoe UI", 9, "bold"), anchor="w").pack(fill="x", padx=16, pady=(2, 2))
        self.sessions_frame = tk.Frame(sb, bg=theme.SIDEBAR)
        self.sessions_frame.pack(fill="both", expand=True, padx=8)
        self._refresh_sessions()

        nav = tk.Frame(sb, bg=theme.SIDEBAR)
        nav.pack(fill="x", side="bottom", padx=8, pady=(0, 6))
        for key, ar, en, icon in [
            ("chat", "المحادثة", "Chat", "💬"),
            ("status", "الحالة", "Status", "◉"),
            ("facebook", "فيسبوك", "Facebook", "f"),
            ("tasks", "المهام", "Tasks", "☑"),
            ("backup", "النسخ الاحتياطي", "Backup", "☁"),
            ("settings", "الإعدادات", "Settings", "⚙"),
        ]:
            self._nav_button(nav, f"{icon}  {self.t(ar,en)}", lambda k=key: self.navigate(k), key).pack(fill="x", pady=1)

        status_box = tk.Frame(nav, bg=theme.PANEL, highlightthickness=1, highlightbackground=theme.BORDER)
        status_box.pack(fill="x", pady=(8, 2))
        for key, label in [
            ("hammer", "Hammer"),
            ("facebook", "Facebook"),
            ("backup", self.t("Backup", "Backup")),
            ("task", self.t("المهمة", "Task")),
        ]:
            row = tk.Frame(status_box, bg=theme.PANEL)
            row.pack(fill="x", padx=9, pady=3)
            tk.Label(row, text=label, bg=theme.PANEL, fg=theme.MUTED, font=("Segoe UI", 8)).pack(side="left")
            val = tk.Label(row, text="—", bg=theme.PANEL, fg=theme.TEXT, font=("Segoe UI", 8, "bold"), anchor="e")
            val.pack(side="right", fill="x", expand=True)
            self._sidebar_status_labels[key] = val

    def _nav_button(self, parent, text: str, command, key: str):
        active = key == self.current_view
        return tk.Button(
            parent, text=text, command=command, anchor="w", relief="flat", bd=0,
            bg=theme.SIDEBAR_ACTIVE if active else theme.SIDEBAR,
            activebackground=theme.SIDEBAR_HOVER, fg=theme.TEXT,
            highlightthickness=0,
            font=("Segoe UI", 10, "bold" if active else "normal"), padx=10, pady=7, cursor="hand2",
        )

    def _build_header(self):
        assert self.main is not None
        header = tk.Frame(self.main, bg=theme.PANEL, height=58, highlightthickness=1, highlightbackground=theme.BORDER)
        header.grid(row=0, column=0, sticky="ew")
        header.grid_propagate(False)
        header.grid_columnconfigure(0, weight=1)
        self.main_header = header
        self.header_title = tk.Label(header, text="", bg=theme.PANEL, fg=theme.TEXT, font=("Segoe UI", 12, "bold"))
        self.header_title.grid(row=0, column=0, sticky="w", padx=20, pady=16)
        self.header_agent = tk.Label(header, text="Hammer 2.1", bg=theme.SIDEBAR_ACTIVE, fg=theme.ACCENT,
                                     font=("Segoe UI", 9, "bold"), padx=9, pady=5)
        self.header_agent.grid(row=0, column=1, padx=6)
        ttk.Button(header,text=self.t("ربط الهاتف  QR", "Pair phone  QR"),style="Accent.TButton",command=self.open_phone_pairing).grid(row=0,column=4,padx=(0,12))
        self.global_search = ttk.Entry(header, width=28)
        self.global_search.grid(row=0, column=2, padx=6)
        self.global_search.bind("<Return>", lambda _e: self._global_search())
        self.search_button=ttk.Button(header, text=self.t("بحث", "Search"), command=self._global_search)
        self.search_button.grid(row=0, column=3, padx=(0, 16))
        def resize_header(event):
            if event.width<900:
                self.global_search.grid_remove();self.search_button.grid_remove()
            else:
                self.global_search.grid();self.search_button.grid()
        header.bind('<Configure>',resize_header)

    def open_phone_pairing(self):
        self.navigate("settings")
        if isinstance(self._view_widget, SettingsView):
            self._view_widget.show_category("pairing")

    def _view_title(self, view: str) -> str:
        return {
            "home": self.t("الرئيسية", "Home"), "chat": self.t("المحادثة", "Chat"),
            "status": self.t("الحالة", "Status"), "facebook": "Facebook",
            "tasks": self.t("المهام", "Tasks"), "backup": self.t("النسخ الاحتياطي", "Backup"),
            "settings": self.t("الإعدادات", "Settings"),
        }.get(view, view)

    def _clear_content(self):
        self.chat_window = None
        self._view_widget = None
        if self.content:
            for child in self.content.winfo_children():
                child.destroy()

    # ---------- navigation ----------
    def navigate(self, view: str):
        if not self.content:
            return
        assert self.runtime and self.facebook and self.backup and self.browser_bridge
        if view == "chat":
            if not self.current_session_id:
                self.current_session_id = self.db.create_session("hammer")  # type: ignore[union-attr]
            self.show_chat_session(self.current_session_id)
            return
        self.current_view = view
        self.settings_obj.last_page = view
        self.settings_obj.save()
        self._clear_content()
        self._refresh_sessions()
        self.header_title.config(text=self._view_title(view))
        if view == "home":
            widget = HomeView(self.content, self.settings_obj, self.runtime, self.facebook, self.backup,
                              self.browser_bridge, on_navigate=self.navigate, on_new_chat=self.new_chat, on_pair_phone=self.open_phone_pairing, remote_status=self.remote_status_text)
        elif view == "status":
            widget = ActivityView(self.content, self.facebook, self.settings_obj, self.runtime, self.backup, self.browser_bridge)
        elif view == "facebook":
            widget = FacebookView(self.content, self.settings_obj, self.facebook, self.browser_bridge, on_ask_hammer=self._ask_hammer)
        elif view == "tasks":
            widget = TasksView(self.content, self.settings_obj, self.facebook)
        elif view == "backup":
            widget = BackupView(self.content, self.settings_obj, self.backup)
        elif view == "settings":
            widget = SettingsView(self.content, self.settings_obj, self._settings_saved, self.security, remote_status=self.remote_status_text)
        else:
            return
        self._view_widget = widget
        widget.grid(row=0, column=0, sticky="nsew")
        self._rebuild_nav_highlight()

    def new_chat(self):
        assert self.db
        sid = self.db.create_session("hammer")
        self.show_chat_session(sid)

    def show_chat_session(self, session_id: int):
        assert self.db and self.runtime and self.facebook and self.backup
        session = self.db.get_session(session_id)
        if not session:
            session_id = self.db.create_session("hammer")
        self.current_session_id = int(session_id)
        self.current_view = "chat"
        self.settings_obj.last_page = "chat"
        self.settings_obj.save()
        self._clear_content()
        self.header_title.config(text=self._view_title("chat"))
        self._refresh_sessions()
        self.chat_window = ChatWindow(
            self.content, self.settings_obj, self.current_session_id, self.facebook, self.runtime,
            backup_service=self.backup, on_activity=self._refresh_visible_view,
            on_session_title_changed=self._refresh_sessions, on_voice_request=self._voice_request,
        )
        self._view_widget = self.chat_window
        self.chat_window.grid(row=0, column=0, sticky="nsew")
        self._rebuild_nav_highlight()

    def _ask_hammer(self, text: str):
        if not self.current_session_id:
            self.current_session_id = self.db.create_session("hammer")  # type: ignore[union-attr]
        self.show_chat_session(self.current_session_id)
        self.after(50, lambda: self.chat_window and self.chat_window.prefill_and_send(text))

    # ---------- sessions ----------
    def _refresh_sessions(self):
        if not self.sessions_frame or not self.db:
            return
        for w in self.sessions_frame.winfo_children():
            w.destroy()
        query = self.session_search_var.get().strip() if self.session_search_var else ""
        sessions = self.db.search_sessions(query, 20) if query else self.db.list_sessions(20)
        for s in sessions:
            sid = int(s["id"])
            title = str(s.get("title") or self.t("محادثة جديدة", "New chat"))
            if len(title) > 31:
                title = title[:30] + "…"
            prefix = "📌 " if int(s.get("pinned") or 0) else ""
            active = sid == self.current_session_id and self.current_view == "chat"
            btn = tk.Button(
                self.sessions_frame, text=prefix + title, command=lambda x=sid: self.show_chat_session(x),
                anchor="w", relief="flat", bd=0,
                highlightthickness=0,
                bg=theme.SIDEBAR_ACTIVE if active else theme.SIDEBAR,
                activebackground=theme.SIDEBAR_HOVER, fg=theme.TEXT, font=("Segoe UI", 9), padx=8, pady=6, cursor="hand2",
            )
            btn.bind("<Button-3>", lambda e, row=s: self._session_menu(e, row))
            btn.pack(fill="x", pady=1)

    def _session_menu(self, event, session: dict):
        if not self.db:
            return
        sid = int(session["id"])
        menu = tk.Menu(self, tearoff=0)
        menu.add_command(label=self.t("إعادة تسمية", "Rename"), command=lambda: self._rename_session(sid, str(session.get("title") or "")))
        if int(session.get("pinned") or 0):
            menu.add_command(label=self.t("إلغاء التثبيت", "Unpin"), command=lambda: self._update_session_flag(sid, pinned=False))
        else:
            menu.add_command(label=self.t("تثبيت", "Pin"), command=lambda: self._update_session_flag(sid, pinned=True))
        menu.add_command(label=self.t("أرشفة", "Archive"), command=lambda: self._update_session_flag(sid, archived=True))
        if int(session.get("is_private") or 0):
            menu.add_command(label=self.t("إلغاء الوضع الخاص", "Make non-private"), command=lambda: self._update_session_flag(sid, is_private=False))
        else:
            menu.add_command(label=self.t("جعلها خاصة", "Make private"), command=lambda: self._update_session_flag(sid, is_private=True))
        if int(session.get("memory_enabled", 1)):
            menu.add_command(label=self.t("لا تستخدمها للذاكرة", "Disable memory for chat"), command=lambda: self._update_session_flag(sid, memory_enabled=False))
        else:
            menu.add_command(label=self.t("السماح بالذاكرة", "Enable memory for chat"), command=lambda: self._update_session_flag(sid, memory_enabled=True))
        menu.add_separator()
        menu.add_command(label=self.t("حذف", "Delete"), command=lambda: self._delete_session(sid))
        menu.tk_popup(event.x_root, event.y_root)

    def _rename_session(self, sid: int, current: str):
        name = simpledialog.askstring(self.t("إعادة تسمية", "Rename"), self.t("اسم المحادثة", "Chat name"), initialvalue=current, parent=self)
        if name:
            self.db.update_session(sid, title=name.strip())  # type: ignore[union-attr]
            self._refresh_sessions()

    def _update_session_flag(self, sid: int, **kwargs):
        self.db.update_session(sid, **kwargs)  # type: ignore[union-attr]
        self._refresh_sessions()

    def _delete_session(self, sid: int):
        if not messagebox.askyesno(self.t("حذف المحادثة", "Delete chat"), self.t("هل تريد حذف هذه المحادثة؟", "Delete this chat?"), parent=self):
            return
        self.db.delete_session(sid)  # type: ignore[union-attr]
        if self.current_session_id == sid:
            self.current_session_id = None
            self.new_chat()
        else:
            self._refresh_sessions()

    def _global_search(self):
        if not self.db:
            return
        q = self.global_search.get().strip()
        if not q:
            return
        results = self.db.global_search(q, limit=80)
        dlg = tk.Toplevel(self)
        dlg.title(self.t("البحث الشامل", "Global search"))
        dlg.geometry("760x520")
        dlg.transient(self)
        frame = ttk.Frame(dlg, padding=16); frame.pack(fill="both", expand=True)
        ttk.Label(frame, text=self.t(f"نتائج البحث عن: {q}", f"Results for: {q}"), style="CardTitle.TLabel").pack(anchor="w", pady=(0, 10))
        tree = ttk.Treeview(frame, columns=("kind", "title", "detail"), show="headings")
        tree.heading("kind", text=self.t("النوع", "Type")); tree.heading("title", text=self.t("العنوان", "Title")); tree.heading("detail", text=self.t("التفاصيل", "Details"))
        tree.column("kind", width=110, stretch=False); tree.column("title", width=220); tree.column("detail", width=380)
        tree.pack(fill="both", expand=True)
        for row in results:
            tree.insert("", "end", values=(row.get("type", row.get("kind", "")), row.get("title", ""), row.get("detail", "")))
        if not results:
            tree.insert("", "end", values=("—", self.t("لا توجد نتائج", "No results"), ""))

    # ---------- settings / status ----------
    def _settings_saved(self, settings: Settings):
        old_lang = self.settings_obj.interface_language
        old_appearance = self.settings_obj.appearance
        self.settings_obj = settings
        assert self.runtime and self.facebook and self.backup
        self.runtime.reconfigure(settings.context_tokens, settings.threads, retry_count=settings.hammer_retry_count, performance_mode=settings.performance_mode)
        self.facebook.update_settings(settings)
        self.backup.update_settings(settings)
        self._restart_remote_worker()
        self._activity("settings_saved", f"language={settings.interface_language}; appearance={settings.appearance}; ctx={settings.context_tokens}; threads={settings.threads}")
        try:
            from ..startup import apply_startup_mode
            apply_startup_mode(settings.start_with_windows)
        except Exception as exc:
            self._activity("startup_setting_error", f"{type(exc).__name__}: {exc}")
        if settings.interface_language != old_lang or settings.appearance != old_appearance:
            theme.apply(settings.appearance)
            self._styles()
            sid = self.current_session_id
            view = self.current_view
            self.show_main(sid)
            self.navigate(view if view in {"home","chat","status","facebook","tasks","backup","settings"} else "home")
            return
        if self.chat_window:
            self.chat_window.apply_settings(settings)
        self._backup_after_change()
        self._refresh_visible_view()

    def _stop_remote_worker(self):
        worker = getattr(self, "remote_worker", None)
        self.remote_worker = None
        if worker:
            try:
                worker.stop()
            except Exception as exc:
                self._activity("remote_stop_error", type(exc).__name__)

    def _restart_remote_worker(self):
        self._stop_remote_worker()
        if not self.settings_obj.remote_enabled:
            self._remote_status = self.t("اتصال الهاتف غير مفعّل", "Phone connection is disabled")
            return
        worker = None
        try:
            from ..remote.service import build_remote_worker
            worker = build_remote_worker(self.settings_obj, self.security, self.db, self.runtime, self.facebook, activity=self._activity)
            if worker:
                worker.start()
                self.remote_worker = worker
                self._remote_status = self.t("اتصال Android مفعّل", "Android connection is enabled")
            else:
                self._remote_status = self.t("اتصال الهاتف غير مفعّل", "Phone connection is disabled")
        except Exception as exc:
            if worker:
                try:
                    worker.stop()
                except Exception:
                    pass
            # Pairing credentials must never appear in UI errors or activity logs.
            self._remote_status = self.t("تعذر تشغيل اتصال Android. راجع مفتاح الاقتران والمنفذ وإعدادات الاتصال.", "Could not start Android connection. Check the pairing token, port and connection settings.")
            self._activity("remote_start_error", type(exc).__name__)

    def remote_status_text(self):
        worker = getattr(self, "remote_worker", None)
        if worker:
            return worker.status_text()
        return self._remote_status

    def _refresh_visible_view(self):
        try:
            if self._view_widget and hasattr(self._view_widget, "refresh"):
                self._view_widget.refresh()
        except Exception:
            pass
        self._refresh_status_card()

    def _refresh_status_card(self):
        if not self._sidebar_status_labels or not self.runtime or not self.facebook or not self.backup:
            return
        self._sidebar_status_labels["hammer"].config(text=self.t("جاهز", "Ready") if self.runtime.loaded_profile else self.t("عند الطلب", "On demand"))
        fb = self.facebook.status_text()
        fb_short = fb.split(" — ")[0]
        self._sidebar_status_labels["facebook"].config(text=fb_short[:20])
        bst = self.backup.status()
        self._sidebar_status_labels["backup"].config(text=self.t("متزامن", "Synced") if bst.connected and bst.last_sync else self.t("محلي", "Local"))
        st = self.facebook.current_status()
        self._sidebar_status_labels["task"].config(text=self.t("شغالة", "Running") if st.get("running") else self.t("لا يوجد", "None"))

    def _rebuild_nav_highlight(self):
        # Rebuilding the sidebar is cheap and keeps active-state styling consistent.
        if not self.sidebar:
            return
        # Preserve session search text while rebuilding.
        q = self.session_search_var.get() if self.session_search_var else ""
        for child in self.sidebar.winfo_children():
            child.destroy()
        self._sidebar_status_labels = {}
        self._build_sidebar()
        if self.session_search_var:
            self.session_search_var.set(q)
            self._refresh_sessions()
        self._refresh_status_card()

    def _schedule_background_polls(self):
        if self._poll_after_id:
            try: self.after_cancel(self._poll_after_id)
            except Exception: pass
        if self._idle_after_id:
            try: self.after_cancel(self._idle_after_id)
            except Exception: pass
        self._poll_after_id = self.after(1200, self._poll_status)
        self._idle_after_id = self.after(30_000, self._poll_idle_unload)
        self._backup_after_id = self.after(60_000, self._poll_backup_sync)

    def _poll_status(self):
        if not self.winfo_exists():
            return
        self._refresh_status_card()
        self._poll_after_id = self.after(1200, self._poll_status)

    def _poll_idle_unload(self):
        if not self.winfo_exists() or not self.runtime:
            return
        try:
            if self.runtime.unload_if_idle(self.settings_obj.hammer_idle_minutes):
                self._activity("hammer_idle_unload", f"idle_minutes={self.settings_obj.hammer_idle_minutes}")
        except Exception as exc:
            self._activity("ai_error", f"idle-unload: {type(exc).__name__}: {exc}")
        self._idle_after_id = self.after(30_000, self._poll_idle_unload)
        self._backup_after_id = self.after(60_000, self._poll_backup_sync)

    def _poll_backup_sync(self):
        if not self.winfo_exists() or not self.backup:
            return
        try:
            if self.settings_obj.auto_backup and not self._backup_sync_running:
                from datetime import datetime
                st=self.backup.status()
                last=st.last_sync if self.settings_obj.drive_sync_enabled and st.connected else st.last_backup
                due=True
                if last:
                    try:
                        elapsed=(datetime.now()-datetime.fromisoformat(last)).total_seconds()/60
                        due=elapsed >= max(15,int(self.settings_obj.drive_sync_interval_minutes))
                    except Exception:
                        due=True
                if due:
                    self._backup_sync_running=True
                    def work():
                        try:
                            if self.settings_obj.drive_sync_enabled and self.backup.status().connected:
                                self.backup.sync_now()
                            else:
                                self.backup.create_local_backup()
                        except Exception as exc:
                            self._activity("backup_error",f"auto: {type(exc).__name__}: {exc}")
                        finally:
                            self._backup_sync_running=False
                    threading.Thread(target=work,daemon=True,name="yaa-auto-backup").start()
        finally:
            self._backup_after_id=self.after(60_000,self._poll_backup_sync)

    def _backup_after_change(self):
        if not self.backup or not self.settings_obj.auto_backup or self._backup_sync_running:
            return
        self._backup_sync_running=True
        def work():
            try:self.backup.create_local_backup()
            except Exception as exc:self._activity("backup_error",f"change: {type(exc).__name__}: {exc}")
            finally:self._backup_sync_running=False
        threading.Thread(target=work,daemon=True,name="yaa-change-backup").start()

    # ---------- voice ----------
    def _voice_request(self, chat: ChatWindow):
        if not self.settings_obj.voice_enabled:
            messagebox.showinfo(self.t("الصوت", "Voice"), self.t("فعّل الصوت من Settings > Voice أولًا.", "Enable voice in Settings > Voice first."), parent=self)
            return
        try:
            from ..voice.service import VoiceService
            svc = VoiceService(self.settings_obj)
        except Exception as exc:
            messagebox.showerror(self.t("الصوت", "Voice"), str(exc), parent=self)
            return

        def work():
            try:
                text = svc.listen_once()
            except Exception as exc:
                self.after(0, lambda: messagebox.showerror(self.t("الصوت", "Voice"), str(exc), parent=self))
                return
            if text:
                self.after(0, lambda: chat.prefill_and_send(text))
        threading.Thread(target=work, daemon=True, name="yaa-voice-listen").start()

    # ---------- close/tray ----------
    def _on_close_request(self):
        mode = self.settings_obj.close_behavior
        if mode == "ask":
            answer = messagebox.askyesnocancel(
                self.t("إغلاق البرنامج", "Close app"),
                self.t("نعم = إغلاق كامل\nلا = إبقاءه بالخلفية", "Yes = exit completely\nNo = keep running in background"),
                parent=self,
            )
            if answer is None:
                return
            mode = "exit" if answer else "tray"
        if mode == "tray":
            if self._ensure_tray():
                self.withdraw()
                return
            # Safe fallback when the optional system tray backend is unavailable.
            self.iconify()
            return
        self._shutdown()

    def _ensure_tray(self) -> bool:
        if self.tray:
            return True
        try:
            from .tray import TrayController
            self.tray = TrayController(self, on_open=self._restore_from_tray, on_exit=self._shutdown)
            self.tray.start()
            return True
        except Exception as exc:
            self._activity("tray_error", f"{type(exc).__name__}: {exc}")
            return False

    def _restore_from_tray(self):
        self.after(0, self._restore_window)

    def _restore_window(self):
        self.deiconify(); self.state("normal"); self.lift(); self.focus_force()

    def _shutdown(self):
        self._stop_remote_worker()
        try:
            if self.tray:
                self.tray.stop()
        except Exception:
            pass
        try:
            if self.browser_bridge:
                self.browser_bridge.stop()
        except Exception:
            pass
        try:
            if self.facebook:
                self.facebook.shutdown()
        except Exception:
            pass
        try:
            if self.runtime:
                self.runtime.stop(wait=False)
        except Exception:
            pass
        self.destroy()
