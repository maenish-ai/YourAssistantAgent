from __future__ import annotations

import threading
import tkinter as tk
from tkinter import ttk, messagebox

from ..agent.facebook_service import FacebookService
from ..storage.db import ChatDB
from .i18n import ui_text


class FacebookView(ttk.Frame):
    def __init__(self, master, settings, facebook: FacebookService, browser_bridge=None, on_ask_hammer=None):
        super().__init__(master, padding=22)
        self.settings = settings
        self.language = settings.interface_language
        self.facebook = facebook
        self.browser_bridge = browser_bridge
        self.on_ask_hammer = on_ask_hammer or (lambda text: None)
        self.db = ChatDB()
        self._busy = False
        self._build()
        self.refresh()

    def t(self, ar, en):
        return ui_text(ar, en, self.language)

    def _build(self):
        self.columnconfigure(0, weight=1)
        self.rowconfigure(4, weight=1)
        ttk.Label(self, text="Facebook", style="Title.TLabel").grid(row=0, column=0, sticky="w")
        ttk.Label(self, text=self.t("لوحة العمل: الاتصال، الجروبات، وحالة التنفيذ.", "Workspace for connection, groups and execution status."), style="Muted.TLabel").grid(row=1, column=0, sticky="w", pady=(3, 14))

        cards = ttk.Frame(self)
        cards.grid(row=2, column=0, sticky="ew")
        for i in range(4): cards.columnconfigure(i, weight=1)
        self.connection = self._card(cards, 0, self.t("الحساب", "Account"), "—")
        self.groups = self._card(cards, 1, self.t("الجروبات", "Groups"), "0")
        self.bridge = self._card(cards, 2, self.t("المتصفح المفتوح", "Open browser"), "—")
        self.task = self._card(cards, 3, self.t("المهمة الحالية", "Current task"), "—")

        controls = ttk.LabelFrame(self, text=self.t("الاتصال والإدارة", "Connection & management"), padding=12)
        controls.grid(row=3, column=0, sticky="ew", pady=(14, 10))
        ttk.Button(controls, text=self.t("تسجيل الدخول", "Login"), command=lambda: self._run("login")).pack(side="left", padx=4)
        ttk.Button(controls, text=self.t("فحص الاتصال", "Check connection"), command=lambda: self._run("verify")).pack(side="left", padx=4)
        ttk.Button(controls, text=self.t("تحديث الجروبات", "Refresh groups"), command=lambda: self._run("discover")).pack(side="left", padx=4)
        ttk.Button(controls, text=self.t("تحديث الشاشة", "Refresh view"), command=self.refresh).pack(side="left", padx=4)
        self.op_status = ttk.Label(controls, text="", style="Muted.TLabel")
        self.op_status.pack(side="left", padx=12)

        main = ttk.Frame(self)
        main.grid(row=4, column=0, sticky="nsew")
        main.columnconfigure(0, weight=3); main.columnconfigure(1, weight=2); main.rowconfigure(1, weight=1)

        search_bar = ttk.Frame(main)
        search_bar.grid(row=0, column=0, sticky="ew", padx=(0, 8), pady=(0, 6))
        self.search_var = tk.StringVar()
        search = ttk.Entry(search_bar, textvariable=self.search_var)
        search.pack(side="left", fill="x", expand=True)
        search.bind("<KeyRelease>", lambda e: self.refresh_groups())
        ttk.Button(search_bar, text=self.t("بحث", "Search"), command=self.refresh_groups).pack(side="left", padx=6)

        group_box = ttk.LabelFrame(main, text=self.t("الجروبات المحفوظة", "Saved groups"), padding=8)
        group_box.grid(row=1, column=0, sticky="nsew", padx=(0, 8))
        group_box.rowconfigure(0, weight=1); group_box.columnconfigure(0, weight=1)
        self.tree = ttk.Treeview(group_box, columns=("name", "tags"), show="headings")
        self.tree.heading("name", text=self.t("الاسم", "Name")); self.tree.heading("tags", text=self.t("التصنيف", "Tags"))
        self.tree.column("name", width=340); self.tree.column("tags", width=150)
        self.tree.grid(row=0, column=0, sticky="nsew")
        sb = ttk.Scrollbar(group_box, orient="vertical", command=self.tree.yview); sb.grid(row=0, column=1, sticky="ns"); self.tree.config(yscrollcommand=sb.set)

        hammer = ttk.LabelFrame(main, text=self.t("اسأل Hammer ضمن Facebook", "Ask Hammer in Facebook"), padding=12)
        hammer.grid(row=0, column=1, rowspan=2, sticky="nsew")
        hammer.rowconfigure(1, weight=1); hammer.columnconfigure(0, weight=1)
        ttk.Label(hammer, text=self.t("اكتب أمرًا مثل: انشر آخر منشور على جروبات خلدة الساعة 8.", "Example: share the latest post to Khalda groups at 8 PM."), style="Muted.TLabel", wraplength=340).grid(row=0, column=0, sticky="w", pady=(0, 8))
        self.command = tk.Text(hammer, height=8, wrap="word")
        self.command.grid(row=1, column=0, sticky="nsew")
        ttk.Button(hammer, text=self.t("إرسال إلى Hammer", "Send to Hammer"), style="Accent.TButton", command=self._send_to_hammer).grid(row=2, column=0, sticky="e", pady=(10, 0))

    def _card(self, parent, col, title, value):
        box = ttk.LabelFrame(parent, text=title, padding=10)
        box.grid(row=0, column=col, sticky="nsew", padx=(0 if col == 0 else 5, 5 if col < 3 else 0))
        lbl = ttk.Label(box, text=value, style="CardTitle.TLabel", wraplength=175)
        lbl.pack(anchor="w")
        return lbl

    def _send_to_hammer(self):
        text = self.command.get("1.0", "end-1c").strip()
        if not text:
            return
        selected = self.tree.selection()
        if selected:
            values = self.tree.item(selected[0], "values")
            if values:
                text += self.t(f"\nالمجموعة المحددة حاليًا: {values[0]}", f"\nCurrently selected group: {values[0]}")
        self.on_ask_hammer(text)

    def _run(self, action):
        if self._busy:
            return
        self._busy = True
        self.op_status.config(text=self.t("جاري التنفيذ…", "Working…"))
        def work():
            if action == "login": result = self.facebook.open_manual_login()
            elif action == "verify": result = self.facebook.verify_session()
            else: result = self.facebook.discover_groups()
            self.after(0, lambda: self._done(result.message))
        threading.Thread(target=work, daemon=True, name=f"yaa-facebook-ui-{action}").start()

    def _done(self, message):
        self._busy = False
        self.op_status.config(text=message)
        self.refresh()

    def refresh_groups(self):
        for iid in self.tree.get_children(): self.tree.delete(iid)
        for g in self.db.list_groups(keyword=self.search_var.get().strip(), limit=1000, enabled_only=False):
            self.tree.insert("", "end", iid=str(g["id"]), values=(g["name"], g.get("tags") or ""))

    def refresh(self):
        self.connection.config(text=self.facebook.status_text())
        self.groups.config(text=str(self.db.count_groups()))
        if self.browser_bridge is None:
            bridge = self.t("غير متاح", "Not available")
        elif self.browser_bridge.connected:
            browser = self.browser_bridge.browser or self.t("المتصفح", "browser")
            tabs = self.browser_bridge.tabs
            bridge = self.t(f"متصل — {browser} — {tabs} تبويب", f"Connected — {browser} — {tabs} tab(s)")
        else:
            bridge = self.t("غير متصل", "Not connected")
        self.bridge.config(text=bridge)
        st = self.facebook.current_status()
        if st["running"]:
            self.task.config(text=f"#{st['active_rule_id']} • {st['step']} • {st['done']}/{st['total']}")
        else:
            self.task.config(text=self.t("لا توجد مهمة", "No active task"))
        self.refresh_groups()
