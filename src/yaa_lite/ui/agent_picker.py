from __future__ import annotations

import tkinter as tk
from tkinter import ttk

from ..ai.profiles import ARABIC, GENERAL
from .resources import asset_path
from . import theme


class AgentPicker(ttk.Frame):
    def __init__(self, master, on_select, remember_default=False):
        super().__init__(master, padding=28)
        self.on_select = on_select
        self.remember = tk.BooleanVar(value=remember_default)
        self._brand_image = None
        self.columnconfigure(0, weight=1)

        try:
            self._brand_image = tk.PhotoImage(file=str(asset_path("brand_mark_128.png")))
            ttk.Label(self, image=self._brand_image).grid(row=0, column=0, sticky="w", pady=(4, 8))
        except Exception:
            pass
        ttk.Label(self, text="Your Assistant Agent", style="Title.TLabel").grid(row=1, column=0, sticky="w", pady=(0, 2))
        ttk.Label(self, text="Choose your agent", style="CardTitle.TLabel").grid(row=2, column=0, sticky="w", pady=(6, 4))
        ttk.Label(
            self,
            text="اختر الوكيل قبل الدخول. لن يتم تحميل أي نموذج حتى تبدأ المحادثة.",
            style="Muted.TLabel",
        ).grid(row=3, column=0, sticky="w", pady=(0, 24))
        self._card(ARABIC, 4)
        self._card(GENERAL, 5)
        ttk.Checkbutton(
            self,
            text="Remember my choice / تذكّر اختياري",
            variable=self.remember,
        ).grid(row=6, column=0, sticky="w", pady=(18, 0))

    def _card(self, profile, row):
        box = ttk.Frame(self, style="Card.TFrame", padding=16)
        box.grid(row=row, column=0, sticky="ew", pady=7)
        box.columnconfigure(0, weight=1)
        ttk.Label(box, text=profile.title, style="CardTitle.TLabel").grid(row=0, column=0, sticky="w")
        ttk.Label(box, text=profile.subtitle, style="Muted.TLabel").grid(row=1, column=0, sticky="w", pady=(4, 0))
        ttk.Button(
            box,
            text="اختيار / Select",
            command=lambda p=profile: self.on_select(p.key, self.remember.get()),
            style="Accent.TButton",
        ).grid(row=0, column=1, rowspan=2, padx=(20, 0))
