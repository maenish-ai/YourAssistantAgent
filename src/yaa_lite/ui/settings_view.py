from __future__ import annotations

import tkinter as tk
from tkinter import ttk

from ..agent.hammer_agent import HAMMER_LICENSE, HAMMER_MODEL_LABEL
from ..config import Settings
from .i18n import ui_text


class SettingsView(ttk.Frame):
    def __init__(self, master, settings: Settings, on_save):
        super().__init__(master, padding=24)
        self.settings = settings
        self.on_save = on_save
        self.language = settings.interface_language or "bilingual"
        self._build()

    def t(self, ar: str, en: str) -> str:
        return ui_text(ar, en, self.language)

    def _section(self, row: int, title: str, subtitle: str = "") -> ttk.Frame:
        box = ttk.LabelFrame(self, text=title, padding=14)
        box.grid(row=row, column=0, sticky="ew", pady=(0, 14))
        box.columnconfigure(1, weight=1)
        if subtitle:
            ttk.Label(box, text=subtitle, style="Muted.TLabel", wraplength=760).grid(row=0, column=0, columnspan=2, sticky="w", pady=(0, 10))
        return box

    def _build(self):
        self.columnconfigure(0, weight=1)
        ttk.Label(self, text=self.t("الإعدادات", "Settings"), style="Title.TLabel").grid(row=0, column=0, sticky="w", pady=(0, 6))
        ttk.Label(
            self,
            text=self.t("واجهة مرتبة: اللغة، Hammer Smart Agent، Facebook، والأداء.", "Organized settings for language, Hammer Smart Agent, Facebook and performance."),
            style="Muted.TLabel",
        ).grid(row=1, column=0, sticky="w", pady=(0, 18))

        ui_box = self._section(2, self.t("الواجهة واللغة", "Interface & language"))
        ttk.Label(ui_box, text=self.t("لغة الواجهة", "Interface language")).grid(row=1, column=0, sticky="w", pady=6)
        self.language_combo = ttk.Combobox(ui_box, state="readonly", values=["العربية + English", "العربية", "English"], width=24)
        self.language_combo.grid(row=1, column=1, sticky="w", pady=6)
        self.language_combo.set({"bilingual": "العربية + English", "ar": "العربية", "en": "English"}.get(self.settings.interface_language, "العربية + English"))
        ttk.Label(ui_box, text=self.t("لغة الرد", "Reply language")).grid(row=2, column=0, sticky="w", pady=6)
        ttk.Label(ui_box, text=self.t("تلقائي حسب لغة رسالتك", "Automatic — follows your message language"), style="Muted.TLabel").grid(row=2, column=1, sticky="w", pady=6)

        smart_box = self._section(
            3,
            self.t("الوكيل الذكي", "Smart Agent"),
            self.t("موديل واحد فقط ظاهر للمستخدم. Hammer يتولى اختيار الأدوات والمحادثة، مع بوابة موافقة قبل الإجراءات الخارجية.", "One visible assistant. Hammer handles tool routing and conversation, with confirmation before external actions."),
        )
        ttk.Label(smart_box, text=self.t("الموديل", "Model")).grid(row=1, column=0, sticky="w", pady=6)
        ttk.Label(smart_box, text=HAMMER_MODEL_LABEL, style="CardTitle.TLabel").grid(row=1, column=1, sticky="w", pady=6)
        ttk.Label(smart_box, text=self.t("الترخيص", "License")).grid(row=2, column=0, sticky="w", pady=6)
        ttk.Label(smart_box, text=f"{HAMMER_LICENSE} — Personal / non-commercial", style="Muted.TLabel").grid(row=2, column=1, sticky="w", pady=6)
        self.smart_var = tk.BooleanVar(value=self.settings.smart_agent_enabled)
        ttk.Checkbutton(smart_box, text=self.t("تفعيل الوكيل الذكي", "Enable Smart Agent"), variable=self.smart_var).grid(row=3, column=0, columnspan=2, sticky="w", pady=5)
        self.confirm_var = tk.BooleanVar(value=self.settings.confirm_external_actions)
        ttk.Checkbutton(smart_box, text=self.t("اطلب موافقتي قبل النشر أو التغيير الخارجي", "Ask for approval before publishing or external changes"), variable=self.confirm_var).grid(row=4, column=0, columnspan=2, sticky="w", pady=5)
        ttk.Label(smart_box, text=self.t("التشغيل", "Runtime")).grid(row=5, column=0, sticky="w", pady=6)
        ttk.Label(smart_box, text=self.t("محلي بالكامل عبر llama.cpp — يحمل عند أول طلب فقط", "Fully local via llama.cpp — lazy loads on first real request"), style="Muted.TLabel").grid(row=5, column=1, sticky="w", pady=6)

        fb_box = self._section(4, "Facebook", self.t("احفظ صفحة المصدر مرة واحدة ليستخدمها الوكيل في الأوامر الطبيعية.", "Save the source page once so the agent can reuse it in natural commands."))
        ttk.Label(fb_box, text=self.t("صفحة المصدر الافتراضية", "Default source page")).grid(row=1, column=0, sticky="w", pady=6)
        self.source_page = ttk.Entry(fb_box, width=68)
        self.source_page.grid(row=1, column=1, sticky="ew", pady=6)
        self.source_page.insert(0, self.settings.default_source_page or "")

        perf_box = self._section(5, self.t("الأداء — أجهزة 4GB RAM", "Performance — 4GB RAM"))
        ttk.Label(perf_box, text="Context").grid(row=1, column=0, sticky="w", pady=6)
        self.context = ttk.Combobox(perf_box, state="readonly", values=[512, 768, 1024], width=12)
        self.context.grid(row=1, column=1, sticky="w", pady=6)
        self.context.set(str(self.settings.context_tokens))
        ttk.Label(perf_box, text="CPU threads").grid(row=2, column=0, sticky="w", pady=6)
        self.threads = ttk.Combobox(perf_box, state="readonly", values=[1, 2], width=12)
        self.threads.grid(row=2, column=1, sticky="w", pady=6)
        self.threads.set(str(self.settings.threads))
        ttk.Label(perf_box, text=self.t("حد الرد", "Max reply tokens")).grid(row=3, column=0, sticky="w", pady=6)
        self.max_tokens = ttk.Combobox(perf_box, state="readonly", values=[96, 128, 160, 220, 256], width=12)
        self.max_tokens.grid(row=3, column=1, sticky="w", pady=6)
        self.max_tokens.set(str(self.settings.max_response_tokens))
        ttk.Label(perf_box, text=self.t("مهلة AI بالثواني", "AI timeout seconds")).grid(row=4, column=0, sticky="w", pady=6)
        self.timeout = ttk.Combobox(perf_box, state="readonly", values=[45, 60, 75, 90, 120, 150], width=12)
        self.timeout.grid(row=4, column=1, sticky="w", pady=6)
        self.timeout.set(str(self.settings.ai_timeout_seconds))
        self.retry_var = tk.BooleanVar(value=self.settings.retry_ai_once)
        ttk.Checkbutton(perf_box, text=self.t("إعادة محاولة واحدة بوضع ذاكرة خفيف عند سقوط الاتصال", "Retry once in low-memory mode if the AI connection drops"), variable=self.retry_var).grid(row=5, column=0, columnspan=2, sticky="w", pady=6)
        ttk.Label(perf_box, text=self.t("الموصى به: Context 768، Threads 2. Hammer هو الموديل الوحيد في الذاكرة.", "Recommended: Context 768, Threads 2. Hammer is the only model loaded in memory."), style="Muted.TLabel").grid(row=6, column=0, columnspan=2, sticky="w", pady=(8, 0))

        actions = ttk.Frame(self)
        actions.grid(row=6, column=0, sticky="ew", pady=(4, 0))
        ttk.Button(actions, text=self.t("حفظ وتطبيق", "Save & apply"), style="Accent.TButton", command=self.save).pack(side="left")
        self.status = ttk.Label(actions, text="", style="Muted.TLabel")
        self.status.pack(side="left", padx=12)

    def save(self):
        lang = {"العربية + English": "bilingual", "العربية": "ar", "English": "en"}.get(self.language_combo.get(), "bilingual")
        self.settings.interface_language = lang
        self.settings.selected_agent = "hammer"
        self.settings.remember_agent = True
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
        self.status.config(text=ui_text("تم الحفظ", "Saved", lang))
