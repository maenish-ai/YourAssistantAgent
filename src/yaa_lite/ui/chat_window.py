from __future__ import annotations

import queue
import threading
import tkinter as tk
from pathlib import Path
from tkinter import filedialog, messagebox, ttk

from ..ai.engine import ChatEngine
from ..ai.profiles import get_profile
from ..ai.runtime import LocalAIRuntime
from ..config import Settings
from ..storage.db import ChatDB
from . import theme
from .resources import asset_path

class ChatWindow(ttk.Frame):
    def __init__(self, master, agent_key: str, settings: Settings, on_change_agent):
        super().__init__(master, padding=0)
        self.settings = settings
        self.profile = get_profile(agent_key)
        self.on_change_agent = on_change_agent
        self.db = ChatDB()
        self.runtime = LocalAIRuntime(settings.context_tokens, settings.threads)
        self.engine = ChatEngine(self.runtime)
        self.result_q: queue.Queue = queue.Queue()
        self.busy = False
        self.attachments: list[str] = []
        self._brand_image = None
        self._build()
        self._load_history()
        self.after(100, self._poll_results)

    def _build(self):
        self.columnconfigure(0, weight=1)
        self.rowconfigure(1, weight=1)
        top = ttk.Frame(self, padding=(16, 10))
        top.grid(row=0, column=0, sticky="ew")
        top.columnconfigure(2, weight=1)
        try:
            self._brand_image = tk.PhotoImage(file=str(asset_path("brand_mark_64.png")))
            ttk.Label(top, image=self._brand_image).grid(row=0, column=0, sticky="w", padx=(0, 8))
        except Exception:
            pass
        ttk.Label(top, text="Your Assistant Agent", style="CardTitle.TLabel").grid(row=0, column=1, sticky="w")
        self.agent_label = ttk.Label(top, text=f"{self.profile.title} • AI loads on first real request", style="Muted.TLabel")
        self.agent_label.grid(row=0, column=2, sticky="w", padx=12)
        ttk.Button(top, text="Change agent", command=self._change_agent).grid(row=0, column=3, padx=4)
        ttk.Button(top, text="Stop AI", command=self._stop_ai).grid(row=0, column=4, padx=4)

        body = ttk.Frame(self, padding=(18, 6))
        body.grid(row=1, column=0, sticky="nsew")
        body.columnconfigure(0, weight=1)
        body.rowconfigure(0, weight=1)
        self.chat = tk.Text(body, wrap="word", state="disabled", relief="flat", bg=theme.BG, fg=theme.TEXT, font=("Segoe UI", 10), padx=8, pady=8)
        self.chat.grid(row=0, column=0, sticky="nsew")
        scroll = ttk.Scrollbar(body, orient="vertical", command=self.chat.yview)
        scroll.grid(row=0, column=1, sticky="ns")
        self.chat.configure(yscrollcommand=scroll.set)
        self.chat.tag_configure("user_name", font=("Segoe UI", 9, "bold"), foreground=theme.ACCENT, spacing1=8)
        self.chat.tag_configure("assistant_name", font=("Segoe UI", 9, "bold"), foreground="#087f5b", spacing1=8)
        self.chat.tag_configure("msg", spacing3=8, lmargin1=6, lmargin2=6)

        composer = ttk.Frame(self, padding=(18, 10, 18, 16))
        composer.grid(row=2, column=0, sticky="ew")
        composer.columnconfigure(0, weight=1)
        self.input = tk.Text(composer, height=3, wrap="word", relief="solid", bd=1, font=("Segoe UI", 10), padx=8, pady=7)
        self.input.grid(row=0, column=0, sticky="ew")
        self.input.bind("<Return>", self._on_enter)
        self.input.bind("<Shift-Return>", self._on_shift_enter)
        controls = ttk.Frame(composer)
        controls.grid(row=1, column=0, sticky="ew", pady=(8, 0))
        self.status = ttk.Label(controls, text="Ready", style="Muted.TLabel")
        self.status.pack(side="left")
        ttk.Button(controls, text="Attach", command=self._attach).pack(side="right", padx=4)
        self.send_btn = ttk.Button(controls, text="Send", style="Accent.TButton", command=self.send)
        self.send_btn.pack(side="right")

    def _load_history(self):
        for m in self.db.recent_messages(self.profile.key, 30):
            self._append(m["role"], m["content"])

    def _append(self, role: str, text: str):
        self.chat.configure(state="normal")
        if role == "user":
            self.chat.insert("end", "You\n", "user_name")
        else:
            self.chat.insert("end", f"{self.profile.title}\n", "assistant_name")
        self.chat.insert("end", text.strip() + "\n", "msg")
        self.chat.configure(state="disabled")
        self.chat.see("end")

    def _on_enter(self, event):
        if event.state & 0x0001:  # shift on Windows/Tk
            return None
        self.send()
        return "break"

    def _on_shift_enter(self, event):
        return None

    def _attach(self):
        paths = filedialog.askopenfilenames(title="Attach files")
        if paths:
            self.attachments.extend(paths)
            self.status.config(text=f"{len(self.attachments)} attachment(s) ready")

    def send(self):
        if self.busy:
            return
        text = self.input.get("1.0", "end-1c").strip()
        if not text:
            return
        if self.attachments:
            names = ", ".join(Path(p).name for p in self.attachments)
            text_for_ai = f"{text}\n\nAttached task files: {names}"
        else:
            text_for_ai = text
        self.input.delete("1.0", "end")
        self._append("user", text)
        self.db.add_message("user", text, self.profile.key)
        history = self.db.recent_messages(self.profile.key, 8)
        self.busy = True
        self.send_btn.state(["disabled"])
        self.status.config(text="Working in background…")

        def work():
            try:
                reply = self.engine.reply(
                    self.profile, history[:-1], text_for_ai,
                    max_tokens=self.settings.max_response_tokens,
                    timeout=self.settings.ai_timeout_seconds,
                    status=lambda s: self.result_q.put(("status", s)),
                )
                self.result_q.put(("reply", reply.text))
            except Exception as e:
                self.result_q.put(("error", str(e)))
        threading.Thread(target=work, daemon=True, name="yaa-ai-worker").start()

    def _poll_results(self):
        try:
            while True:
                kind, value = self.result_q.get_nowait()
                if kind == "status":
                    self.status.config(text=value)
                elif kind == "reply":
                    self._append("assistant", value)
                    self.db.add_message("assistant", value, self.profile.key)
                    self._finish("Ready")
                    self.attachments.clear()
                elif kind == "error":
                    self._append("assistant", "تعذر تشغيل الذكاء المحلي الآن. الواجهة ما زالت شغالة.\n" + value)
                    self.db.add_activity("ai_error", value)
                    self._finish("AI error — app still responsive")
        except queue.Empty:
            pass
        self.after(100, self._poll_results)

    def _finish(self, status):
        self.busy = False
        self.send_btn.state(["!disabled"])
        self.status.config(text=status)
        self.input.focus_set()

    def _stop_ai(self):
        threading.Thread(target=self.runtime.stop, daemon=True).start()
        self.status.config(text="AI stopping in background…")

    def _change_agent(self):
        self._stop_ai()
        self.on_change_agent()

    def shutdown(self):
        self.runtime.stop()
