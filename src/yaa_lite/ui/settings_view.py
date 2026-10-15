from __future__ import annotations

import tkinter as tk
from tkinter import ttk

from ..config import Settings


class SettingsView(ttk.Frame):
    AGENT_LABELS = {"arabic": "Arabic Agent — عربي", "general": "General Agent — عام"}

    def __init__(self, master, settings: Settings, on_save):
        super().__init__(master, padding=24)
        self.settings = settings
        self.on_save = on_save
        self._build()

    def _section(self, row: int, title: str, subtitle: str = "") -> ttk.Frame:
        box = ttk.LabelFrame(self, text=title, padding=14)
        box.grid(row=row, column=0, sticky="ew", pady=(0, 14))
        box.columnconfigure(1, weight=1)
        if subtitle:
            ttk.Label(box, text=subtitle, style="Muted.TLabel", wraplength=680).grid(row=0, column=0, columnspan=2, sticky="w", pady=(0, 10))
        return box

    def _build(self):
        self.columnconfigure(0, weight=1)
        ttk.Label(self, text="الإعدادات", style="Title.TLabel").grid(row=0, column=0, sticky="w", pady=(0, 6))
        ttk.Label(
            self,
            text="إعدادات واضحة مثل تطبيقات المحادثة: الوكيل، Smart Agent، Facebook، والأداء.",
            style="Muted.TLabel",
        ).grid(row=1, column=0, sticky="w", pady=(0, 18))

        agent_box = self._section(2, "الوكيل والمحادثة")
        ttk.Label(agent_box, text="الوكيل الافتراضي").grid(row=1, column=0, sticky="w", pady=6)
        self.agent = ttk.Combobox(agent_box, state="readonly", values=list(self.AGENT_LABELS.values()), width=30)
        self.agent.grid(row=1, column=1, sticky="w", pady=6)
        self.agent.set(self.AGENT_LABELS.get(self.settings.selected_agent or "arabic", self.AGENT_LABELS["arabic"]))
        self.remember_var = tk.BooleanVar(value=self.settings.remember_agent)
        ttk.Checkbutton(agent_box, text="تذكر الوكيل المختار عند فتح البرنامج", variable=self.remember_var).grid(row=2, column=1, sticky="w", pady=6)

        smart_box = self._section(
            3,
            "Smart Agent / الوكيل الذكي",
            "المحادثة العادية تبقى محادثة. أوامر العمل تتحول إلى خطة وأدوات مسموحة فقط؛ لا يوجد تنفيذ Python عشوائي.",
        )
        self.smart_var = tk.BooleanVar(value=self.settings.smart_agent_enabled)
        ttk.Checkbutton(smart_box, text="تفعيل Smart Agent", variable=self.smart_var).grid(row=1, column=0, columnspan=2, sticky="w", pady=5)
        self.confirm_var = tk.BooleanVar(value=self.settings.confirm_external_actions)
        ttk.Checkbutton(smart_box, text="اطلب موافقتي قبل الحفظ أو أي إجراء خارجي", variable=self.confirm_var).grid(row=2, column=0, columnspan=2, sticky="w", pady=5)
        ttk.Label(smart_box, text="محرك الأدوات").grid(row=3, column=0, sticky="w", pady=6)
        ttk.Label(smart_box, text="smolagents-compatible tools — lightweight Apache-2.0 integration", style="Muted.TLabel").grid(row=3, column=1, sticky="w", pady=6)

        fb_box = self._section(4, "Facebook", "حدد صفحة المصدر مرة واحدة، وبعدها تستطيع قول اسم الصفحة بالكلام الطبيعي بدون لصق الرابط في كل مرة.")
        ttk.Label(fb_box, text="رابط صفحة المصدر الافتراضية").grid(row=1, column=0, sticky="w", pady=6)
        self.source_page = ttk.Entry(fb_box, width=66)
        self.source_page.grid(row=1, column=1, sticky="ew", pady=6)
        self.source_page.insert(0, self.settings.default_source_page or "")

        perf_box = self._section(5, "الأداء — مناسب لأجهزة 4GB RAM")
        ttk.Label(perf_box, text="Context").grid(row=1, column=0, sticky="w", pady=6)
        self.context = ttk.Combobox(perf_box, state="readonly", values=[512, 768, 1024], width=12)
        self.context.grid(row=1, column=1, sticky="w", pady=6)
        self.context.set(str(self.settings.context_tokens))
        ttk.Label(perf_box, text="CPU threads").grid(row=2, column=0, sticky="w", pady=6)
        self.threads = ttk.Combobox(perf_box, state="readonly", values=[1, 2], width=12)
        self.threads.grid(row=2, column=1, sticky="w", pady=6)
        self.threads.set(str(self.settings.threads))
        ttk.Label(perf_box, text="Max reply tokens").grid(row=3, column=0, sticky="w", pady=6)
        self.max_tokens = ttk.Combobox(perf_box, state="readonly", values=[96, 128, 160, 220, 256], width=12)
        self.max_tokens.grid(row=3, column=1, sticky="w", pady=6)
        self.max_tokens.set(str(self.settings.max_response_tokens))
        ttk.Label(perf_box, text="AI timeout (seconds)").grid(row=4, column=0, sticky="w", pady=6)
        self.timeout = ttk.Combobox(perf_box, state="readonly", values=[45, 60, 75, 90, 120], width=12)
        self.timeout.grid(row=4, column=1, sticky="w", pady=6)
        self.timeout.set(str(self.settings.ai_timeout_seconds))
        self.retry_var = tk.BooleanVar(value=self.settings.retry_ai_once)
        ttk.Checkbutton(perf_box, text="أعد تشغيل الذكاء مرة تلقائيًا بوضع خفيف عند سقوط الاتصال", variable=self.retry_var).grid(row=5, column=0, columnspan=2, sticky="w", pady=6)
        ttk.Label(perf_box, text="الموصى به: Context 768، Threads 2، Reply 160. يتم تحميل موديل واحد فقط في الذاكرة.", style="Muted.TLabel").grid(row=6, column=0, columnspan=2, sticky="w", pady=(8, 0))

        actions = ttk.Frame(self)
        actions.grid(row=6, column=0, sticky="ew", pady=(4, 0))
        ttk.Button(actions, text="حفظ وتطبيق", style="Accent.TButton", command=self.save).pack(side="left")
        self.status = ttk.Label(actions, text="", style="Muted.TLabel")
        self.status.pack(side="left", padx=12)

    def save(self):
        reverse = {v: k for k, v in self.AGENT_LABELS.items()}
        self.settings.selected_agent = reverse.get(self.agent.get(), "arabic")
        self.settings.remember_agent = bool(self.remember_var.get())
        self.settings.smart_agent_enabled = bool(self.smart_var.get())
        self.settings.confirm_external_actions = bool(self.confirm_var.get())
        self.settings.default_source_page = self.source_page.get().strip()
        self.settings.context_tokens = int(self.context.get())
        self.settings.threads = int(self.threads.get())
        self.settings.max_response_tokens = int(self.max_tokens.get())
        self.settings.ai_timeout_seconds = int(self.timeout.get())
        self.settings.retry_ai_once = bool(self.retry_var.get())
        self.settings.save()
        self.on_save(self.settings)
        self.status.config(text="تم الحفظ. لا يتم تحميل AI إلا عند الحاجة.")
