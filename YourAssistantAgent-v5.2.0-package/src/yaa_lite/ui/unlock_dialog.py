from __future__ import annotations

import tkinter as tk
from tkinter import ttk, messagebox

from ..security.manager import SecurityManager, SecurityError
from .i18n import ui_text


class UnlockDialog(tk.Toplevel):
    def __init__(self, master, security: SecurityManager, language: str, on_unlocked):
        super().__init__(master)
        self.security = security
        self.language = language
        self.on_unlocked = on_unlocked
        self.use_recovery = False
        self.title(ui_text("فتح Your Assistant Agent", "Unlock Your Assistant Agent", language))
        self.geometry("460x300")
        self.resizable(False, False)
        self.transient(master)
        self.grab_set()
        self.protocol("WM_DELETE_WINDOW", master.destroy)
        frame = ttk.Frame(self, padding=28)
        frame.pack(fill="both", expand=True)
        ttk.Label(frame, text=ui_text("مرحبًا برجوعك", "Welcome back", language), style="Title.TLabel").pack(anchor="w", pady=(0, 8))
        ttk.Label(frame, text=ui_text("أدخل كلمة المرور لفتح البرنامج.", "Enter your password to unlock the app.", language), style="Muted.TLabel").pack(anchor="w", pady=(0, 20))
        self.label = ttk.Label(frame, text=ui_text("كلمة المرور", "Password", language))
        self.label.pack(anchor="w")
        self.entry = ttk.Entry(frame, show="•")
        self.entry.pack(fill="x", pady=(6, 14))
        self.entry.bind("<Return>", lambda e: self.unlock())
        row = ttk.Frame(frame)
        row.pack(fill="x")
        ttk.Button(row, text=ui_text("فتح", "Unlock", language), style="Accent.TButton", command=self.unlock).pack(side="right")
        self.switch_btn = ttk.Button(row, text=ui_text("استخدم مفتاح الاسترداد", "Use recovery key", language), command=self.toggle_recovery)
        self.switch_btn.pack(side="left")
        self.status = ttk.Label(frame, text="", style="Muted.TLabel")
        self.status.pack(anchor="w", pady=(12, 0))
        self.after(100, self.entry.focus_set)

    def toggle_recovery(self):
        self.use_recovery = not self.use_recovery
        self.entry.delete(0, "end")
        self.entry.config(show="" if self.use_recovery else "•")
        if self.use_recovery:
            self.label.config(text=ui_text("مفتاح الاسترداد", "Recovery key", self.language))
            self.switch_btn.config(text=ui_text("استخدم كلمة المرور", "Use password", self.language))
        else:
            self.label.config(text=ui_text("كلمة المرور", "Password", self.language))
            self.switch_btn.config(text=ui_text("استخدم مفتاح الاسترداد", "Use recovery key", self.language))

    def unlock(self):
        secret = self.entry.get().strip()
        try:
            if self.use_recovery:
                self.security.unlock_with_recovery(secret)
            else:
                self.security.unlock_with_password(secret)
        except SecurityError:
            self.status.config(text=ui_text("بيانات الفتح غير صحيحة.", "Incorrect unlock information.", self.language))
            return
        self.grab_release()
        self.destroy()
        self.on_unlocked()
