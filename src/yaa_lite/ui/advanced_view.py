from __future__ import annotations

import os
import subprocess
import sys
import threading
from pathlib import Path
import tkinter as tk
from tkinter import ttk

from ..agent.facebook_service import FacebookService
from ..agent.tools import SMOLAGENTS_AVAILABLE
from ..ai.runtime import log_path
from ..config import Settings, config_dir, data_dir
from ..storage.db import ChatDB


def _open_path(path: Path) -> None:
    try:
        if os.name == "nt":
            os.startfile(str(path))  # type: ignore[attr-defined]
        elif sys.platform == "darwin":
            subprocess.Popen(["open", str(path)])
        else:
            subprocess.Popen(["xdg-open", str(path)])
    except Exception:
        pass


class AdvancedView(ttk.Frame):
    def __init__(self, master, facebook: FacebookService, settings: Settings, on_activity=None):
        super().__init__(master, padding=24)
        self.facebook = facebook
        self.settings = settings
        self.on_activity = on_activity
        self.db = ChatDB()
        self._busy = False
        self._build()
        self.refresh()

    def _build(self):
        self.columnconfigure(0, weight=1)
        ttk.Label(self, text="متقدم", style="Title.TLabel").grid(row=0, column=0, sticky="w", pady=(0, 6))
        ttk.Label(
            self,
            text="اتصالات وأدوات متقدمة. لا يتم فتح المتصفح أو تحميل الذكاء عند فتح البرنامج.",
            style="Muted.TLabel",
        ).grid(row=1, column=0, sticky="w", pady=(0, 16))

        fb = ttk.LabelFrame(self, text="Facebook", padding=14)
        fb.grid(row=2, column=0, sticky="ew", pady=(0, 14))
        fb.columnconfigure(1, weight=1)
        ttk.Label(fb, text="الحالة").grid(row=0, column=0, sticky="w", padx=(0, 12), pady=4)
        self.fb_status = ttk.Label(fb, text="—", style="Muted.TLabel")
        self.fb_status.grid(row=0, column=1, sticky="w", pady=4)
        ttk.Label(fb, text="المجموعات المحفوظة").grid(row=1, column=0, sticky="w", padx=(0, 12), pady=4)
        self.group_count = ttk.Label(fb, text="0", style="Muted.TLabel")
        self.group_count.grid(row=1, column=1, sticky="w", pady=4)
        btns = ttk.Frame(fb)
        btns.grid(row=2, column=0, columnspan=2, sticky="w", pady=(10, 2))
        ttk.Button(btns, text="ربط / تسجيل دخول", command=lambda: self._run_async("login")).pack(side="left", padx=(0, 6))
        ttk.Button(btns, text="فحص الاتصال", command=lambda: self._run_async("verify")).pack(side="left", padx=6)
        ttk.Button(btns, text="تحديث المجموعات", command=lambda: self._run_async("discover")).pack(side="left", padx=6)
        self.op_status = ttk.Label(fb, text="", style="Muted.TLabel", wraplength=680)
        self.op_status.grid(row=3, column=0, columnspan=2, sticky="w", pady=(8, 0))

        agent = ttk.LabelFrame(self, text="Smart Agent", padding=14)
        agent.grid(row=3, column=0, sticky="ew", pady=(0, 14))
        ttk.Label(agent, text="Framework").grid(row=0, column=0, sticky="w", padx=(0, 12), pady=4)
        ttk.Label(
            agent,
            text="smolagents-compatible lightweight tool contracts" if SMOLAGENTS_AVAILABLE else "Built-in smolagents-compatible tool contracts",
            style="Muted.TLabel",
        ).grid(row=0, column=1, sticky="w", pady=4)
        ttk.Label(agent, text="التنفيذ").grid(row=1, column=0, sticky="w", padx=(0, 12), pady=4)
        ttk.Label(agent, text="Allow-listed tools + confirmation gate; no arbitrary CodeAgent execution", style="Muted.TLabel").grid(row=1, column=1, sticky="w", pady=4)
        ttk.Label(agent, text="المهام المحفوظة").grid(row=2, column=0, sticky="w", padx=(0, 12), pady=4)
        self.rules_count = ttk.Label(agent, text="0", style="Muted.TLabel")
        self.rules_count.grid(row=2, column=1, sticky="w", pady=4)

        tools = ttk.LabelFrame(self, text="Diagnostics", padding=14)
        tools.grid(row=4, column=0, sticky="ew")
        ttk.Label(tools, text=f"AI log: {log_path()}", wraplength=700).grid(row=0, column=0, sticky="w", pady=3)
        ttk.Label(tools, text=f"Data: {data_dir()}", wraplength=700).grid(row=1, column=0, sticky="w", pady=3)
        ttk.Label(tools, text=f"Config: {config_dir()}", wraplength=700).grid(row=2, column=0, sticky="w", pady=3)
        ttk.Button(tools, text="فتح مجلد البيانات", command=lambda: _open_path(data_dir())).grid(row=3, column=0, sticky="w", pady=(10, 2))
        ttk.Button(tools, text="فتح مجلد سجل AI", command=lambda: _open_path(log_path().parent)).grid(row=4, column=0, sticky="w", pady=2)

    def _run_async(self, action: str):
        if self._busy:
            return
        self._busy = True
        self.op_status.config(text="جاري التنفيذ في الخلفية…")

        def work():
            if action == "login":
                result = self.facebook.open_manual_login()
            elif action == "verify":
                result = self.facebook.verify_session()
            else:
                result = self.facebook.discover_groups()
            self.after(0, lambda: self._done(result.message))

        threading.Thread(target=work, daemon=True, name=f"yaa-advanced-{action}").start()

    def _done(self, message: str):
        self._busy = False
        self.op_status.config(text=message)
        self.refresh()
        if self.on_activity:
            self.on_activity()

    def refresh(self):
        self.fb_status.config(text=self.facebook.status_text())
        self.group_count.config(text=str(self.db.count_groups()))
        self.rules_count.config(text=str(len(self.db.list_rules(500))))
