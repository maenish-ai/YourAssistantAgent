from __future__ import annotations

import queue
import re
import threading
import tkinter as tk
from pathlib import Path
from tkinter import filedialog, ttk, messagebox

from ..agent.facebook_service import FacebookService
from ..agent.orchestrator import SmartAgentController, AgentResponse
from ..ai.engine import ChatEngine
from ..ai.profiles import QWEN
from ..ai.runtime import LocalAIError, LocalAIRuntime
from ..backup.service import BackupService
from ..config import Settings
from ..storage.db import ChatDB
from . import theme
from .i18n import ui_text

_ARABIC_RE = re.compile(r"[\u0600-\u06ff]")


class ChatWindow(ttk.Frame):
    def __init__(self, master, settings: Settings, session_id: int, facebook_service: FacebookService,
                 runtime: LocalAIRuntime, backup_service: BackupService | None = None,
                 on_activity=None, on_session_title_changed=None, on_voice_request=None):
        super().__init__(master, padding=0)
        self.settings = settings
        self.profile = QWEN
        self.session_id = int(session_id)
        self.on_activity = on_activity
        self.on_session_title_changed = on_session_title_changed
        self.on_voice_request = on_voice_request
        self.db = ChatDB()
        self.runtime = runtime
        self.engine = ChatEngine(self.runtime)
        self.controller = SmartAgentController(self.db, settings, self.engine, facebook_service, backup_service)
        self.result_q: queue.Queue = queue.Queue()
        self.busy = False
        self.attachments: list[str] = []
        self.last_detail = ""
        self._voice_turn_started = False
        self._build(); self._load_history(); self.after(100, self._poll_results)

    def t(self, ar: str, en: str) -> str: return ui_text(ar, en, self.settings.interface_language)
    @property
    def agent_key(self) -> str: return "hammer"  # database compatibility key

    def _build(self):
        self.columnconfigure(0, weight=1); self.rowconfigure(1, weight=1)
        top=ttk.Frame(self,padding=(28,12,28,4));top.grid(row=0,column=0,sticky="ew");top.columnconfigure(0,weight=1)
        ttk.Label(top,text=self.settings.assistant_name or "Your Assistant Agent",style="CardTitle.TLabel").grid(row=0,column=0,sticky="w")
        initial = self.t("Qwen3 • جاهز","Qwen3 • ready") if self.runtime.loaded_profile else self.t("Qwen3 • يتم التجهيز بالخلفية","Qwen3 • preparing in background")
        self.model_state=ttk.Label(top,text=initial,style="Muted.TLabel");self.model_state.grid(row=0,column=1,sticky="e")

        body=ttk.Frame(self,padding=(28,4,28,0));body.grid(row=1,column=0,sticky="nsew");body.columnconfigure(0,weight=1);body.rowconfigure(0,weight=1)
        self.chat=tk.Text(body,wrap="word",state="disabled",relief="flat",borderwidth=0,highlightthickness=0,bg=theme.BG,fg=theme.TEXT,font=("Segoe UI",10),padx=18,pady=14,spacing1=2,spacing3=6)
        self.chat.grid(row=0,column=0,sticky="nsew");scroll=ttk.Scrollbar(body,orient="vertical",command=self.chat.yview);scroll.grid(row=0,column=1,sticky="ns");self.chat.configure(yscrollcommand=scroll.set)
        self.chat.tag_configure("user_name",font=("Segoe UI",9,"bold"),foreground=theme.ACCENT,spacing1=12)
        self.chat.tag_configure("assistant_name",font=("Segoe UI",9,"bold"),foreground=theme.SUCCESS,spacing1=12)
        self.chat.tag_configure("msg_ltr",spacing3=12,lmargin1=8,lmargin2=8,rmargin=40,justify="left")
        self.chat.tag_configure("msg_rtl",spacing3=12,lmargin1=40,lmargin2=40,rmargin=8,justify="right")
        self.chat.tag_configure("system_hint",foreground=theme.MUTED,justify="center",spacing1=8,spacing3=10)

        details=ttk.Frame(self,padding=(28,4,28,0));details.grid(row=2,column=0,sticky="ew")
        self.detail_btn=ttk.Button(details,text=self.t("عرض التفاصيل","View details"),command=self._toggle_details)
        self.detail_btn.pack(side="right");self.detail_btn.pack_forget()
        self.detail_box=tk.Text(details,height=4,wrap="word",state="disabled",relief="solid",borderwidth=1,bg=theme.PANEL,fg=theme.MUTED,font=("Consolas",9));self.detail_box.pack(fill="x",pady=4);self.detail_box.pack_forget()

        composer_outer=ttk.Frame(self,padding=(28,8,28,18));composer_outer.grid(row=3,column=0,sticky="ew");composer_outer.columnconfigure(0,weight=1)
        composer=tk.Frame(composer_outer,bg=theme.INPUT,highlightbackground=theme.BORDER,highlightcolor=theme.ACCENT,highlightthickness=1,bd=0);composer.grid(row=0,column=0,sticky="ew");composer.columnconfigure(0,weight=1)
        self.input=tk.Text(composer,height=3,wrap="word",relief="flat",bd=0,highlightthickness=0,bg=theme.INPUT,fg=theme.TEXT,insertbackground=theme.TEXT,font=("Segoe UI",10),padx=12,pady=10)
        self.input.grid(row=0,column=0,columnspan=5,sticky="ew");self.input.bind("<Return>",self._on_enter);self.input.bind("<Shift-Return>",self._on_shift_enter)
        ttk.Button(composer,text="＋",width=3,command=self._attach).grid(row=1,column=0,sticky="w",padx=(8,2),pady=(0,8))
        ttk.Button(composer,text="🎙",width=3,command=self._voice).grid(row=1,column=1,sticky="w",padx=2,pady=(0,8))
        self.status=ttk.Label(composer,text=self.t("جاهز","Ready"),style="Muted.TLabel");self.status.grid(row=1,column=2,sticky="e",padx=8,pady=(0,8))
        ttk.Button(composer,text=self.t("إيقاف Qwen","Stop Qwen"),command=self.stop_ai).grid(row=1,column=3,sticky="e",padx=4,pady=(0,8))
        self.send_btn=ttk.Button(composer,text=self.t("إرسال ➤","Send ➤"),style="Accent.TButton",command=self.send);self.send_btn.grid(row=1,column=4,sticky="e",padx=(4,8),pady=(0,8))
        ttk.Label(composer_outer,text=self.t("اكتب أو اضغط الميكروفون وتكلم • Enter للإرسال • Shift+Enter لسطر جديد","Type or press the microphone and speak • Enter sends • Shift+Enter for new line"),style="Muted.TLabel").grid(row=1,column=0,sticky="w",pady=(6,0))

    def _load_history(self):
        history=self.db.recent_messages("hammer",80,session_id=self.session_id)
        if not history:self._append_hint(self.t("احكي معي طبيعي أو اضغط الميكروفون. Qwen هو العقل المحلي للمحادثة والمهام.","Talk naturally or press the microphone. Qwen is the local brain for chat and tasks."))
        for m in history:self._append(m["role"],m["content"])

    def _append_hint(self,text):
        self.chat.configure(state="normal");self.chat.insert("end",text.strip()+"\n","system_hint");self.chat.configure(state="disabled");self.chat.see("end")
    def _append(self,role,text):
        self.chat.configure(state="normal")
        if role=="user":self.chat.insert("end",self.t("أنت\n","You\n"),"user_name")
        else:self.chat.insert("end",(self.settings.assistant_name or "Your Assistant Agent")+"\n","assistant_name")
        tag="msg_rtl" if _ARABIC_RE.search(text) else "msg_ltr";self.chat.insert("end",text.strip()+"\n",tag);self.chat.configure(state="disabled");self.chat.see("end")

    def _on_enter(self,event):
        if event.state & 0x0001:return None
        self.send();return "break"
    def _on_shift_enter(self,event):return None

    def _attach(self):
        paths=filedialog.askopenfilenames(title=self.t("إرفاق صور أو ملفات","Attach images or files"))
        if paths:self.attachments.extend(paths);self.status.config(text=self.t(f"{len(self.attachments)} مرفق",f"{len(self.attachments)} attachment(s)"))

    def _voice(self):
        if self.busy:
            return
        self._voice_turn_started = True
        self.status.config(text=self.t("🎙 أسمعك… تكلم الآن","🎙 Listening… speak now"))
        if self.on_voice_request:self.on_voice_request(self)
        else:
            self._voice_turn_started = False
            messagebox.showinfo(self.t("الصوت","Voice"),self.t("خدمة الصوت غير متاحة في هذه النسخة.","Voice service is unavailable in this build."),parent=self)

    def prefill_and_send(self,text:str):
        self.input.delete("1.0","end");self.input.insert("1.0",text);self.send()

    def voice_failed(self, message: str):
        self._voice_turn_started = False
        self.status.config(text=self.t("تعذر فهم الصوت","Voice failed"))
        messagebox.showerror(self.t("الصوت","Voice"), message, parent=self)

    def send(self):
        if self.busy:return
        text=self.input.get("1.0","end-1c").strip()
        if not text:return
        names=", ".join(Path(p).name for p in self.attachments);text_for_ai=f"{text}\n\nAttached task files: {names}" if names else text
        self.input.delete("1.0","end");self._append("user",text);self.db.add_message("user",text,"hammer",self.session_id);self.db.rename_session_from_first_message(self.session_id,text)
        if self.on_session_title_changed:self.on_session_title_changed()
        self.db.add_activity("chat_request",f"session={self.session_id}; {text[:500]}")
        history=self.db.recent_messages("hammer",10,session_id=self.session_id);self.busy=True;self.send_btn.state(["disabled"]);self.status.config(text=self.t("Qwen يحلل…","Qwen is analyzing…"));self.detail_btn.pack_forget();self.detail_box.pack_forget()

        def work():
            try:
                reply=self.controller.handle(QWEN,history[:-1],text_for_ai,self.session_id,self.settings.max_response_tokens,self.settings.ai_timeout_seconds,status=lambda s:self.result_q.put(("status",s)))
                self.result_q.put(("reply",reply))
            except LocalAIError as e:
                detail=f"{type(e.__cause__).__name__ if e.__cause__ else 'LocalAIError'}: {e.__cause__ or e}";self.result_q.put(("ai_error",detail))
            except Exception as e:self.result_q.put(("ai_error",f"{type(e).__name__}: {e}"))
        threading.Thread(target=work,daemon=True,name="yaa-qwen-worker").start()

    def _poll_results(self):
        try:
            while True:
                kind,value=self.result_q.get_nowait()
                if kind=="status":
                    mapping={
                        "Starting Qwen3…":self.t("تشغيل Qwen3…","Starting Qwen3…"),
                        "Qwen3 ready":self.t("Qwen جاهز","Qwen ready"),
                        "Qwen3 is choosing an action…":self.t("Qwen يختار الأداة…","Qwen is choosing a tool…"),
                        "Qwen3 is thinking…":self.t("Qwen يفكر…","Qwen is thinking…"),
                        "Qwen3 is handling the request…":self.t("Qwen ينفذ الطلب…","Qwen is handling the request…"),
                        "Qwen3 failed — retrying in low-memory mode…":self.t("تعطل Qwen — إعادة تشغيل بوضع خفيف…","Qwen failed — restarting in low-memory mode…"),
                        "Qwen3 failed again — final ultra-safe retry…":self.t("تعطل مرة ثانية — آخر محاولة آمنة…","Qwen failed again — final safe retry…"),
                    };self.status.config(text=mapping.get(value,value));self.model_state.config(text=mapping.get(value,value))
                elif kind=="reply":
                    reply:AgentResponse=value;self._append("assistant",reply.text);self.db.add_message("assistant",reply.text,"hammer",self.session_id);self.db.add_activity("chat_reply",f"session={self.session_id}; {reply.text[:500]}");self.last_detail=reply.detail or ""
                    if self.last_detail:self.detail_btn.pack(side="right")
                    self._finish(self.t("جاهز","Ready"));self.attachments.clear();self.model_state.config(text=self.t("Qwen3 • جاهز","Qwen3 • ready"));
                    self._maybe_speak_reply(reply.text)
                    if self.on_activity:self.on_activity()
                elif kind=="ai_error":
                    self.db.add_activity("ai_error",value);self._append("assistant",self.t("Qwen لم يستطع إكمال الرد بعد محاولات إعادة التشغيل. افتح الحالة لرؤية التفاصيل التقنية.","Qwen could not complete the reply after automatic restart attempts. Open Status for technical details."));self.last_detail=value;self.detail_btn.pack(side="right");self._finish(self.t("راجع الحالة","See Status"));
                    if self.on_activity:self.on_activity()
        except queue.Empty:pass
        if self.winfo_exists():self.after(100,self._poll_results)

    def _maybe_speak_reply(self, text: str):
        mode=getattr(self.settings,"voice_reply_mode","voice_if_started")
        explicit_voice_turn=self._voice_turn_started
        enabled=bool(getattr(self.settings,"voice_enabled",True))
        should=explicit_voice_turn or (enabled and mode=="always")
        self._voice_turn_started=False
        if not should:return
        def work():
            try:
                from ..voice.service import VoiceService
                VoiceService(self.settings).speak(text)
            except Exception as exc:
                self.db.add_activity("voice_error",f"{type(exc).__name__}: {exc}")
        threading.Thread(target=work,daemon=True,name="yaa-voice-speak").start()

    def _toggle_details(self):
        if self.detail_box.winfo_ismapped():self.detail_box.pack_forget();return
        self.detail_box.configure(state="normal");self.detail_box.delete("1.0","end");self.detail_box.insert("1.0",self.last_detail);self.detail_box.configure(state="disabled");self.detail_box.pack(fill="x",pady=4)

    def _finish(self,status):self.busy=False;self.send_btn.state(["!disabled"]);self.status.config(text=status);self.input.focus_set()
    def stop_ai(self):threading.Thread(target=lambda:self.runtime.stop(wait=True),daemon=True,name="yaa-stop-ai").start();self.status.config(text=self.t("جاري إيقاف Qwen…","Stopping Qwen…"));self.db.add_activity("ai_stop","qwen")
    def apply_settings(self,settings:Settings):
        self.settings=settings;self.runtime.reconfigure(settings.context_tokens,settings.threads,retry_count=settings.hammer_retry_count,performance_mode=settings.performance_mode);self.controller.update_settings(settings);self.status.config(text=self.t("تم تطبيق الإعدادات","Settings applied"))
    def shutdown(self):pass
