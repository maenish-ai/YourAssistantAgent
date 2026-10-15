from __future__ import annotations

import socket
from datetime import datetime, timedelta
from tkinter import ttk

from ..agent.facebook_service import FacebookService
from ..backup.service import BackupService
from ..storage.db import ChatDB
from .i18n import ui_text


class HomeView(ttk.Frame):
    def __init__(self, master, settings, runtime, facebook: FacebookService, backup: BackupService,
                 browser_bridge=None, on_navigate=None, on_new_chat=None):
        super().__init__(master, padding=24)
        self.settings = settings
        self.runtime = runtime
        self.facebook = facebook
        self.backup = backup
        self.browser_bridge = browser_bridge
        self.on_navigate = on_navigate or (lambda *_: None)
        self.on_new_chat = on_new_chat or (lambda: None)
        self.db = ChatDB()
        self.language = settings.interface_language
        self._build()
        self.refresh()
        self.after(1800, self._auto_refresh)

    def t(self, ar, en):
        return ui_text(ar, en, self.language)

    def _build(self):
        self.columnconfigure(0, weight=1)
        ttk.Label(self, text=self.t("مرحبًا 👋", "Welcome 👋"), style="Title.TLabel").grid(row=0, column=0, sticky="w")
        ttk.Label(self, text=self.t("هذه صورة سريعة عن المساعد والشغل الحالي.", "Here is a quick view of your assistant and current work."), style="Muted.TLabel").grid(row=1, column=0, sticky="w", pady=(4, 18))

        cards = ttk.Frame(self)
        cards.grid(row=2, column=0, sticky="ew")
        for i in range(4):
            cards.columnconfigure(i, weight=1)
        self.hammer = self._card(cards, 0, "Hammer", "—")
        self.fb = self._card(cards, 1, "Facebook", "—")
        self.backup_card = self._card(cards, 2, self.t("النسخ الاحتياطي", "Backup"), "—")
        self.net = self._card(cards, 3, self.t("الإنترنت", "Internet"), "—")

        qa = ttk.LabelFrame(self, text=self.t("إجراءات سريعة", "Quick actions"), padding=14)
        qa.grid(row=3, column=0, sticky="ew", pady=(16, 12))
        ttk.Button(qa, text=self.t("محادثة جديدة", "New chat"), style="Accent.TButton", command=self.on_new_chat).pack(side="left", padx=(0, 8))
        ttk.Button(qa, text=self.t("حالة التنفيذ", "Live status"), command=lambda: self.on_navigate("status")).pack(side="left", padx=8)
        ttk.Button(qa, text="Facebook", command=lambda: self.on_navigate("facebook")).pack(side="left", padx=8)
        ttk.Button(qa, text=self.t("نسخ الآن", "Backup now"), command=self._backup_now).pack(side="left", padx=8)

        middle = ttk.Frame(self)
        middle.grid(row=4, column=0, sticky="nsew")
        middle.columnconfigure(0, weight=1)
        middle.columnconfigure(1, weight=1)
        self.tasks_box = ttk.LabelFrame(middle, text=self.t("المهام القادمة", "Upcoming tasks"), padding=14)
        self.tasks_box.grid(row=0, column=0, sticky="nsew", padx=(0, 7))
        self.suggestions_box = ttk.LabelFrame(middle, text=self.t("اقتراحات Hammer", "Hammer suggestions"), padding=14)
        self.suggestions_box.grid(row=0, column=1, sticky="nsew", padx=(7, 0))

    def _card(self, parent, col, title, value):
        box = ttk.LabelFrame(parent, text=title, padding=12)
        box.grid(row=0, column=col, sticky="nsew", padx=(0 if col == 0 else 5, 5 if col < 3 else 0))
        lbl = ttk.Label(box, text=value, style="CardTitle.TLabel", wraplength=180)
        lbl.pack(anchor="w")
        return lbl

    def _internet(self):
        try:
            with socket.create_connection(("1.1.1.1", 53), timeout=0.4):
                return True
        except OSError:
            return False

    def _backup_now(self):
        try:
            self.backup.create_local_backup()
            self.refresh()
        except Exception as exc:
            self.db.add_activity("backup_error", f"{type(exc).__name__}: {exc}")

    def refresh(self):
        self.hammer.config(text=self.t("جاهز" if self.runtime.loaded_profile else "جاهز عند الطلب", "Ready" if self.runtime.loaded_profile else "Ready on demand"))
        self.fb.config(text=self.facebook.status_text())
        st = self.backup.status()
        self.backup_card.config(text=self.t("متصل" if st.connected else "محلي فقط", "Connected" if st.connected else "Local only"))
        self.net.config(text=self.t("متصل" if self._internet() else "غير متصل", "Online" if self._internet() else "Offline"))

        for w in self.tasks_box.winfo_children():
            w.destroy()
        rules = self.db.list_rules(5)
        if not rules:
            ttk.Label(self.tasks_box, text=self.t("لا توجد مهام مجدولة.", "No scheduled tasks."), style="Muted.TLabel").pack(anchor="w")
        else:
            for r in rules:
                status = self.t("نشطة", "Active") if int(r.get("enabled", 1)) else self.t("متوقفة", "Paused")
                ttk.Label(self.tasks_box, text=f"#{r['id']}  {r['name']}\n{status} • {r.get('next_run_at') or '-'}", wraplength=380).pack(anchor="w", pady=5)

        for w in self.suggestions_box.winfo_children():
            w.destroy()
        suggestions = []
        if self.settings.suggestion_level != "off":
            if self.facebook.status_code() == "not_checked":
                suggestions.append(self.t("افحص اتصال Facebook حتى أعرف إذا الحساب جاهز.", "Check Facebook so I can verify the account is ready."))
            if not st.last_backup:
                suggestions.append(self.t("ما في نسخة احتياطية بعد. اعمل أول Backup.", "No backup exists yet. Create the first backup."))
            if not rules:
                suggestions.append(self.t("إذا عندك شغل متكرر، احكيه لـHammer وحوله لمهمة مجدولة.", "Tell Hammer about recurring work and turn it into a scheduled task."))
        if not suggestions:
            suggestions = [self.t("كل شيء هادئ حاليًا.", "Everything looks quiet right now.")]
        for s in suggestions[:4]:
            ttk.Label(self.suggestions_box, text="• " + s, wraplength=380).pack(anchor="w", pady=4)

    def _auto_refresh(self):
        if self.winfo_exists():
            self.refresh()
            self.after(1800, self._auto_refresh)
