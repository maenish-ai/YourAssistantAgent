from __future__ import annotations

import queue
import re
import threading
import tkinter as tk
from pathlib import Path
from tkinter import filedialog, ttk

from ..agent.facebook_service import FacebookService
from ..agent.orchestrator import SmartAgentController
from ..ai.engine import ChatEngine
from ..ai.profiles import HAMMER
from ..ai.runtime import LocalAIError, LocalAIRuntime
from ..config import Settings
from ..storage.db import ChatDB
from . import theme
from .i18n import ui_text

_ARABIC_RE = re.compile(r"[\u0600-\u06ff]")


class ChatWindow(ttk.Frame):
    def __init__(self, master, agent_key: str, settings: Settings, session_id: int, facebook_service: FacebookService,
                 on_activity=None, on_session_title_changed=None):
        super().__init__(master, padding=0)
        self.settings = settings
        self.profile = HAMMER
        self.session_id = int(session_id)
        self.on_activity = on_activity
        self.on_session_title_changed = on_session_title_changed
        self.db = ChatDB()
        self.runtime = LocalAIRuntime(settings.context_tokens, settings.threads, retry_once=settings.retry_ai_once)
        self.engine = ChatEngine(self.runtime)
        self.controller = SmartAgentController(self.db, settings, self.engine, facebook_service)
        self.result_q: queue.Queue = queue.Queue()
        self.busy = False
        self.attachments: list[str] = []
        self._build()
        self._load_history()
        self.after(100, self._poll_results)

    def t(self, ar: str, en: str) -> str:
        return ui_text(ar, en, self.settings.interface_language)

    @property
    def agent_key(self) -> str:
        return "hammer"

    def _build(self):
        self.columnconfigure(0, weight=1)
        self.rowconfigure(0, weight=1)

        body = ttk.Frame(self, padding=(30, 12, 30, 0))
        body.grid(row=0, column=0, sticky="nsew")
        body.columnconfigure(0, weight=1)
        body.rowconfigure(0, weight=1)

        self.chat = tk.Text(body, wrap="word", state="disabled", relief="flat", borderwidth=0, highlightthickness=0,
                            bg=theme.BG, fg=theme.TEXT, font=("Segoe UI", 10), padx=18, pady=14, spacing1=2, spacing3=6)
        self.chat.grid(row=0, column=0, sticky="nsew")
        scroll = ttk.Scrollbar(body, orient="vertical", command=self.chat.yview)
        scroll.grid(row=0, column=1, sticky="ns")
        self.chat.configure(yscrollcommand=scroll.set)
        self.chat.tag_configure("user_name", font=("Segoe UI", 9, "bold"), foreground=theme.ACCENT, spacing1=12)
        self.chat.tag_configure("assistant_name", font=("Segoe UI", 9, "bold"), foreground="#087f5b", spacing1=12)
        self.chat.tag_configure("msg_ltr", spacing3=12, lmargin1=8, lmargin2=8, rmargin=40, justify="left")
        self.chat.tag_configure("msg_rtl", spacing3=12, lmargin1=40, lmargin2=40, rmargin=8, justify="right")
        self.chat.tag_configure("system_hint", foreground=theme.MUTED, justify="center", spacing1=8, spacing3=10)

        composer_outer = ttk.Frame(self, padding=(30, 8, 30, 18))
        composer_outer.grid(row=1, column=0, sticky="ew")
        composer_outer.columnconfigure(0, weight=1)
        composer = tk.Frame(composer_outer, bg="#ffffff", highlightbackground="#d0d5dd", highlightcolor=theme.ACCENT,
                            highlightthickness=1, bd=0)
        composer.grid(row=0, column=0, sticky="ew")
        composer.columnconfigure(0, weight=1)
        self.input = tk.Text(composer, height=3, wrap="word", relief="flat", bd=0, highlightthickness=0,
                             bg="#ffffff", fg=theme.TEXT, font=("Segoe UI", 10), padx=12, pady=10)
        self.input.grid(row=0, column=0, columnspan=3, sticky="ew")
        self.input.bind("<Return>", self._on_enter)
        self.input.bind("<Shift-Return>", self._on_shift_enter)

        self.attach_btn = ttk.Button(composer, text=self.t("＋ إرفاق", "＋ Attach"), command=self._attach)
        self.attach_btn.grid(row=1, column=0, sticky="w", padx=(8, 4), pady=(0, 8))
        self.status = ttk.Label(composer, text=self.t("جاهز", "Ready"), style="Muted.TLabel")
        self.status.grid(row=1, column=1, sticky="e", padx=8, pady=(0, 8))
        self.send_btn = ttk.Button(composer, text=self.t("إرسال ➤", "Send ➤"), style="Accent.TButton", command=self.send)
        self.send_btn.grid(row=1, column=2, sticky="e", padx=(4, 8), pady=(0, 8))
        ttk.Label(composer_outer,
                  text=self.t("Enter للإرسال • Shift+Enter لسطر جديد • Hammer يخطط والأفعال الخارجية تنتظر موافقتك",
                              "Enter sends • Shift+Enter new line • Hammer plans; external actions wait for approval"),
                  style="Muted.TLabel").grid(row=1, column=0, sticky="w", pady=(6, 0))

    def _load_history(self):
        history = self.db.recent_messages("hammer", 80, session_id=self.session_id)
        if not history:
            self._append_hint(self.t("احكي معي بشكل طبيعي. Hammer 2.1 يقرر إن كانت الرسالة محادثة أو مهمة ويعرض الخطة قبل التنفيذ.",
                                     "Talk naturally. Hammer 2.1 decides whether this is chat or a task and previews actions before execution."))
        for m in history:
            self._append(m["role"], m["content"])

    def _append_hint(self, text: str):
        self.chat.configure(state="normal")
        self.chat.insert("end", text.strip() + "\n", "system_hint")
        self.chat.configure(state="disabled")
        self.chat.see("end")

    def _append(self, role: str, text: str):
        self.chat.configure(state="normal")
        if role == "user":
            self.chat.insert("end", ("أنت\n" if _ARABIC_RE.search(text) else "You\n"), "user_name")
        else:
            self.chat.insert("end", "Your Assistant Agent\n", "assistant_name")
        tag = "msg_rtl" if _ARABIC_RE.search(text) else "msg_ltr"
        self.chat.insert("end", text.strip() + "\n", tag)
        self.chat.configure(state="disabled")
        self.chat.see("end")

    def _on_enter(self, event):
        if event.state & 0x0001:
            return None
        self.send()
        return "break"

    def _on_shift_enter(self, event):
        return None

    def _attach(self):
        paths = filedialog.askopenfilenames(title=self.t("إرفاق صور أو ملفات", "Attach images or files"))
        if paths:
            self.attachments.extend(paths)
            self.status.config(text=self.t(f"{len(self.attachments)} مرفق", f"{len(self.attachments)} attachment(s)"))

    def send(self):
        if self.busy:
            return
        text = self.input.get("1.0", "end-1c").strip()
        if not text:
            return
        names = ", ".join(Path(p).name for p in self.attachments)
        text_for_ai = f"{text}\n\nAttached task files: {names}" if names else text
        self.input.delete("1.0", "end")
        self._append("user", text)
        self.db.add_message("user", text, "hammer", self.session_id)
        self.db.rename_session_from_first_message(self.session_id, text)
        if self.on_session_title_changed:
            self.on_session_title_changed()
        self.db.add_activity("chat_request", f"session={self.session_id}; {text[:500]}")
        history = self.db.recent_messages("hammer", 10, session_id=self.session_id)
        self.busy = True
        self.send_btn.state(["disabled"])
        self.status.config(text=self.t("يفهم طلبك…", "Understanding…"))

        def work():
            try:
                reply = self.controller.handle(HAMMER, history[:-1], text_for_ai, session_id=self.session_id,
                                               max_tokens=self.settings.max_response_tokens,
                                               timeout=self.settings.ai_timeout_seconds,
                                               status=lambda s: self.result_q.put(("status", s)))
                self.result_q.put(("reply", reply.text))
            except LocalAIError as e:
                detail = f"{type(e.__cause__).__name__ if e.__cause__ else 'LocalAIError'}: {e.__cause__ or e}"
                self.result_q.put(("ai_error", detail))
            except Exception as e:
                self.result_q.put(("ai_error", f"{type(e).__name__}: {e}"))

        threading.Thread(target=work, daemon=True, name="yaa-hammer-worker").start()

    def _poll_results(self):
        try:
            while True:
                kind, value = self.result_q.get_nowait()
                if kind == "status":
                    friendly = {
                        "Starting Hammer 2.1…": self.t("تشغيل Hammer 2.1…", "Starting Hammer 2.1…"),
                        "Hammer 2.1 ready": self.t("Hammer 2.1 جاهز", "Hammer 2.1 ready"),
                        "Hammer is choosing an action…": self.t("Hammer يختار الأداة المناسبة…", "Hammer is choosing the right tool…"),
                        "Hammer is thinking…": self.t("Hammer يفكر…", "Hammer is thinking…"),
                        "AI connection dropped — retrying once in low-memory mode…": self.t("انقطع AI — إعادة محاولة بوضع خفيف…", "AI connection dropped — retrying in low-memory mode…"),
                    }.get(value, value)
                    self.status.config(text=friendly)
                elif kind == "reply":
                    self._append("assistant", value)
                    self.db.add_message("assistant", value, "hammer", self.session_id)
                    self.db.add_activity("chat_reply", f"session={self.session_id}; {value[:500]}")
                    self._finish(self.t("جاهز", "Ready"))
                    self.attachments.clear()
                    if self.on_activity:
                        self.on_activity()
                elif kind == "ai_error":
                    self.db.add_activity("ai_error", value)
                    self._append("assistant", self.t("تعذر على Hammer إكمال الرد الآن. البرنامج ما زال شغال؛ افتح الحالة للتفاصيل.",
                                                     "Hammer could not complete the reply. The app is still running; open Status for details."))
                    self._finish(self.t("راجع الحالة", "See Status"))
                    if self.on_activity:
                        self.on_activity()
        except queue.Empty:
            pass
        if self.winfo_exists():
            self.after(100, self._poll_results)

    def _finish(self, status):
        self.busy = False
        self.send_btn.state(["!disabled"])
        self.status.config(text=status)
        self.input.focus_set()

    def stop_ai(self):
        threading.Thread(target=lambda: self.runtime.stop(wait=True), daemon=True, name="yaa-stop-ai").start()
        self.status.config(text=self.t("جاري إيقاف AI…", "Stopping AI…"))
        self.db.add_activity("ai_stop", "hammer")

    def apply_settings(self, settings: Settings):
        self.settings = settings
        self.runtime.reconfigure(settings.context_tokens, settings.threads, settings.retry_ai_once)
        self.controller.update_settings(settings)
        self.status.config(text=self.t("تم تطبيق الإعدادات", "Settings applied"))

    def shutdown(self):
        self.runtime.stop(wait=False)
