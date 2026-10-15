from __future__ import annotations
import tkinter as tk
from tkinter import ttk

from ..ai.profiles import ARABIC, GENERAL
from . import theme

class AgentPicker(ttk.Frame):
    def __init__(self, master, on_select, remember_default=False):
        super().__init__(master, padding=28)
        self.on_select = on_select
        self.remember = tk.BooleanVar(value=remember_default)
        self.columnconfigure(0, weight=1)
        ttk.Label(self, text="Choose your agent", style="Title.TLabel").grid(row=0, column=0, sticky="w", pady=(12, 4))
        ttk.Label(self, text="اختر الوكيل قبل الدخول. لن يتم تحميل أي نموذج حتى تبدأ المحادثة.", style="Muted.TLabel").grid(row=1, column=0, sticky="w", pady=(0, 24))
        self._card(ARABIC, 2)
        self._card(GENERAL, 3)
        ttk.Checkbutton(self, text="Remember my choice / تذكّر اختياري", variable=self.remember).grid(row=4, column=0, sticky="w", pady=(18, 0))

    def _card(self, profile, row):
        box = ttk.Frame(self, style="Card.TFrame", padding=16)
        box.grid(row=row, column=0, sticky="ew", pady=7)
        box.columnconfigure(0, weight=1)
        ttk.Label(box, text=profile.title, style="CardTitle.TLabel").grid(row=0, column=0, sticky="w")
        ttk.Label(box, text=profile.subtitle, style="Muted.TLabel").grid(row=1, column=0, sticky="w", pady=(4, 0))
        ttk.Button(box, text="اختيار / Select", command=lambda p=profile: self.on_select(p.key, self.remember.get()), style="Accent.TButton").grid(row=0, column=1, rowspan=2, padx=(20, 0))
