from __future__ import annotations

import re
import threading
import tkinter as tk
from tkinter import messagebox

from .voice.cloud_service import CloudVoiceService, VoiceCancelled, VoiceError

_APPLIED = False

_FB_STATUS_RE = re.compile(
    r"(?:"
    r"(?:افحص|فحص|تحقق|شيك|تأكد).{0,24}(?:فيس\s*بوك|فيس|facebook)"
    r"|(?:حالة|اتصال).{0,24}(?:فيس\s*بوك|فيس|facebook)"
    r"|(?:فيس\s*بوك|فيس|facebook).{0,24}(?:متصل|الاتصال|حالة|connected|status|connection)"
    r"|check.{0,24}facebook"
    r"|verify.{0,24}facebook"
    r"|facebook.{0,24}(?:status|connection|connected)"
    r")",
    re.IGNORECASE,
)


def _is_facebook_status_request(text: str) -> bool:
    return bool(_FB_STATUS_RE.search(" ".join(str(text or "").split())))


def _clean_visible_text(text: str) -> str:
    value = str(text or "")
    replacements = (
        ("Qwen3 • جاهز", "GroqCloud • GPT-OSS 120B • جاهز"),
        ("Qwen3 • ready", "GroqCloud • GPT-OSS 120B • ready"),
        ("Qwen3", "GroqCloud"),
        ("Qwen", "GroqCloud"),
        ("qwen", "GroqCloud"),
        ("Hammer 2.1 • Local Smart Agent", "GroqCloud • GPT-OSS 120B"),
        ("Hammer 2.1", "GroqCloud"),
        ("Stop GroqCloudCloud", "Stop GroqCloud"),
        ("GroqCloudCloud", "GroqCloud"),
    )
    for old, new in replacements:
        value = value.replace(old, new)
    return value


def _sweep_widget_text(widget) -> None:
    try:
        text = widget.cget("text")
        cleaned = _clean_visible_text(text)
        if cleaned != text:
            widget.configure(text=cleaned)
    except Exception:
        pass
    try:
        for child in widget.winfo_children():
            _sweep_widget_text(child)
    except Exception:
        pass


class _VoicePulseOverlay:
    def __init__(self, chat):
        self.chat = chat
        self.frame = tk.Frame(
            chat,
            bg="#111827",
            highlightthickness=1,
            highlightbackground="#334155",
            bd=0,
        )
        self.title = tk.Label(
            self.frame,
            text="أسمعك… احكي براحتك",
            bg="#111827",
            fg="#f8fafc",
            font=("Segoe UI", 11, "bold"),
        )
        self.title.pack(padx=18, pady=(10, 2))
        self.canvas = tk.Canvas(self.frame, width=300, height=64, bg="#111827", highlightthickness=0)
        self.canvas.pack(padx=14, pady=(0, 4))
        self.hint = tk.Label(
            self.frame,
            text="رح أرسل كلامك تلقائيًا لما تسكت شوي",
            bg="#111827",
            fg="#94a3b8",
            font=("Segoe UI", 9),
        )
        self.hint.pack(padx=12, pady=(0, 5))
        self.stop_btn = tk.Button(
            self.frame,
            text="إيقاف الصوت",
            command=self._stop,
            relief="flat",
            bd=0,
            bg="#1f2937",
            activebackground="#374151",
            fg="#f8fafc",
            padx=12,
            pady=5,
            cursor="hand2",
        )
        self.stop_btn.pack(pady=(0, 10))
        self.frame.place(relx=0.5, rely=0.79, anchor="center")
        self._level = 0.05
        self._pulse = 0
        self._alive = True
        self._draw()

    def _stop(self):
        try:
            self.chat._cloud_voice_live = False
            svc = getattr(self.chat, "_cloud_voice_service", None)
            if svc:
                svc.cancel()
        except Exception:
            pass
        self.close()
        try:
            self.chat.status.config(text=self.chat.t("تم إيقاف الوضع الصوتي", "Voice mode stopped"))
        except Exception:
            pass

    def set_state(self, text: str, hint: str | None = None) -> None:
        if not self._alive:
            return
        try:
            self.title.configure(text=text)
            if hint is not None:
                self.hint.configure(text=hint)
        except Exception:
            pass

    def set_level(self, level: float) -> None:
        self._level = max(0.02, min(float(level), 1.0))

    def _draw(self) -> None:
        if not self._alive:
            return
        try:
            self.canvas.delete("all")
            width = int(self.canvas.cget("width"))
            height = int(self.canvas.cget("height"))
            count = 23
            gap = 4
            bar_w = max(3, (width - gap * (count - 1)) // count)
            center = height / 2
            self._pulse = (self._pulse + 1) % 1000
            for i in range(count):
                distance = abs(i - (count - 1) / 2) / ((count - 1) / 2)
                wave = 0.55 + 0.45 * abs(__import__("math").sin(self._pulse * 0.18 + i * 0.63))
                local = self._level * wave * (1.0 - 0.28 * distance)
                bar_h = max(5, int(7 + local * 48))
                x0 = i * (bar_w + gap)
                x1 = x0 + bar_w
                self.canvas.create_rectangle(x0, center - bar_h / 2, x1, center + bar_h / 2, fill="#e5e7eb", outline="")
            self.chat.after(55, self._draw)
        except Exception:
            self._alive = False

    def close(self) -> None:
        self._alive = False
        try:
            self.frame.destroy()
        except Exception:
            pass


def _ensure_overlay(chat) -> _VoicePulseOverlay:
    overlay = getattr(chat, "_cloud_voice_overlay", None)
    if overlay is None or not getattr(overlay, "_alive", False):
        overlay = _VoicePulseOverlay(chat)
        chat._cloud_voice_overlay = overlay
    return overlay


def _patch_facebook_routing() -> None:
    from .agent.orchestrator import AgentResponse, SmartAgentController

    if getattr(SmartAgentController, "_yaa_cloud_v240_fb", False):
        return
    original = SmartAgentController.handle

    def handle(self, profile, history, user_text, session_id, max_tokens, timeout, status=None):
        if _is_facebook_status_request(user_text):
            try:
                if status:
                    status(self.t("جاري فحص اتصال Facebook…", "Checking Facebook connection…"))
                result = self.tools.execute("verify_facebook_connection", {})
                self._activity("facebook_status_direct", result.text, status)
                if result.ok:
                    text = self.t(
                        f"فحصت اتصال فيسبوك فعليًا. النتيجة: {result.text}",
                        f"I checked the Facebook connection directly. Result: {result.text}",
                    )
                else:
                    text = self.t(
                        f"فحصت اتصال فيسبوك، والنتيجة: {result.text}\nإذا بدك، اطلب مني بعدها أفتح صفحة تسجيل الدخول.",
                        f"I checked the Facebook connection. Result: {result.text}\nIf you want, ask me to open the login page next.",
                    )
                return AgentResponse(text, used_model=False, used_tools=True, detail=f"verify_facebook_connection: {result.text}")
            except Exception as exc:
                return AgentResponse(
                    self.t(f"تعذر فحص اتصال فيسبوك: {exc}", f"Could not verify Facebook connection: {exc}"),
                    used_model=False,
                    used_tools=True,
                    detail=f"verify_facebook_connection error: {type(exc).__name__}: {exc}",
                )
        return original(self, profile, history, user_text, session_id, max_tokens, timeout, status=status)

    SmartAgentController.handle = handle
    SmartAgentController._yaa_cloud_v240_fb = True


def _patch_chat_ui() -> None:
    from .ui.chat_window import ChatWindow

    if getattr(ChatWindow, "_yaa_cloud_v240_ui", False):
        return

    old_build = ChatWindow._build
    old_append = ChatWindow._append
    old_append_hint = ChatWindow._append_hint
    old_poll = ChatWindow._poll_results

    def _build(self):
        old_build(self)
        self._cloud_voice_live = False
        self._cloud_voice_listening = False
        self._cloud_voice_service = None
        self._cloud_voice_overlay = None
        _sweep_widget_text(self)
        try:
            self.model_state.config(text=self.t("GroqCloud • GPT-OSS 120B • جاهز", "GroqCloud • GPT-OSS 120B • ready"))
        except Exception:
            pass

    def _append(self, role, text):
        return old_append(self, role, _clean_visible_text(text))

    def _append_hint(self, text):
        text = _clean_visible_text(text)
        text = text.replace(
            "GroqCloud هو العقل المحلي للمحادثة والمهام.",
            "GroqCloud هو العقل السحابي للمحادثة والمهام.",
        ).replace(
            "GroqCloud is the local brain for chat and tasks.",
            "GroqCloud is the cloud brain for chat and tasks.",
        )
        return old_append_hint(self, text)

    def _poll_results(self):
        result = old_poll(self)
        _sweep_widget_text(self)
        try:
            if not self.busy:
                self.model_state.config(text=self.t("GroqCloud • GPT-OSS 120B • جاهز", "GroqCloud • GPT-OSS 120B • ready"))
        except Exception:
            pass
        return result

    def _voice(self):
        if getattr(self, "busy", False):
            return
        if getattr(self, "_cloud_voice_live", False):
            self._cloud_voice_live = False
            svc = getattr(self, "_cloud_voice_service", None)
            if svc:
                svc.cancel()
            overlay = getattr(self, "_cloud_voice_overlay", None)
            if overlay:
                overlay.close()
            self.status.config(text=self.t("تم إيقاف الوضع الصوتي", "Voice mode stopped"))
            return

        self._cloud_voice_live = True
        self._voice_turn_started = True
        overlay = _ensure_overlay(self)
        overlay.set_state(
            self.t("أسمعك… احكي براحتك", "Listening… speak naturally"),
            self.t("لما تسكت شوي رح أرسل الكلام تلقائيًا", "I will send automatically after a short pause"),
        )
        self.status.config(text=self.t("🎙 أسمعك…", "🎙 Listening…"))
        if self.on_voice_request:
            self.on_voice_request(self)
        else:
            self._cloud_voice_live = False
            overlay.close()
            messagebox.showinfo(
                self.t("الصوت", "Voice"),
                self.t("خدمة الصوت غير متاحة في هذه النسخة.", "Voice service is unavailable in this build."),
                parent=self,
            )

    def voice_failed(self, message: str):
        self._voice_turn_started = False
        self._cloud_voice_live = False
        self._cloud_voice_listening = False
        overlay = getattr(self, "_cloud_voice_overlay", None)
        if overlay:
            overlay.set_state(self.t("ما قدرت أفهم الصوت", "Voice failed"), str(message))
            self.after(1800, overlay.close)
        self.status.config(text=self.t("تعذر فهم الصوت", "Voice failed"))

    def _maybe_speak_reply(self, text: str):
        explicit = bool(getattr(self, "_voice_turn_started", False))
        mode = getattr(self.settings, "voice_reply_mode", "voice_if_started")
        enabled = bool(getattr(self.settings, "voice_enabled", True))
        should = explicit or (enabled and mode == "always")
        self._voice_turn_started = False
        if not should:
            return

        live = bool(getattr(self, "_cloud_voice_live", False))
        overlay = _ensure_overlay(self) if live else None
        if overlay:
            overlay.set_state(
                self.t("برد عليك…", "Replying…"),
                self.t("اضغط إيقاف الصوت متى ما بدك", "Press stop voice whenever you want"),
            )
            overlay.set_level(0.28)

        def work():
            svc = getattr(self, "_cloud_voice_service", None)
            if svc is None:
                svc = CloudVoiceService(self.settings)
                self._cloud_voice_service = svc
            try:
                svc.speak(text)
            except VoiceCancelled:
                return
            except Exception as exc:
                try:
                    self.db.add_activity("voice_error", f"{type(exc).__name__}: {exc}")
                except Exception:
                    pass
            finally:
                if getattr(self, "_cloud_voice_live", False) and self.winfo_exists():
                    self.after(250, lambda: self.on_voice_request(self) if self.on_voice_request else None)
                elif overlay and self.winfo_exists():
                    self.after(0, overlay.close)

        threading.Thread(target=work, daemon=True, name="yaa-cloud-voice-speak").start()

    ChatWindow._build = _build
    ChatWindow._append = _append
    ChatWindow._append_hint = _append_hint
    ChatWindow._poll_results = _poll_results
    ChatWindow._voice = _voice
    ChatWindow.voice_failed = voice_failed
    ChatWindow._maybe_speak_reply = _maybe_speak_reply
    ChatWindow._yaa_cloud_v240_ui = True


def _patch_app_voice() -> None:
    from .ui.app import App

    if getattr(App, "_yaa_cloud_v240_voice", False):
        return

    old_show_main = App.show_main
    old_show_splash = App._show_splash

    def show_main(self, *args, **kwargs):
        result = old_show_main(self, *args, **kwargs)
        _sweep_widget_text(self)
        return result

    def _show_splash(self):
        result = old_show_splash(self)
        try:
            self.after(25, lambda: _sweep_widget_text(self))
        except Exception:
            pass
        return result

    def _voice_request(self, chat):
        if not self.settings_obj.voice_enabled:
            chat._cloud_voice_live = False
            messagebox.showinfo(
                self.t("الصوت", "Voice"),
                self.t("فعّل الصوت من Settings > Voice أولًا.", "Enable voice in Settings > Voice first."),
                parent=self,
            )
            return
        if getattr(chat, "_cloud_voice_listening", False):
            return
        if not getattr(chat, "_cloud_voice_live", False):
            return

        svc = getattr(chat, "_cloud_voice_service", None)
        if svc is None:
            svc = CloudVoiceService(self.settings_obj)
            chat._cloud_voice_service = svc
        else:
            svc.settings = self.settings_obj
            svc.reset_cancel()

        overlay = _ensure_overlay(chat)
        overlay.set_state(
            self.t("أسمعك… احكي براحتك", "Listening… speak naturally"),
            self.t("لما تسكت شوي رح أفهم كلامك وأرد", "I will respond after a short pause"),
        )
        chat._cloud_voice_listening = True

        def level(value: float):
            if chat.winfo_exists():
                chat.after(0, lambda v=value: overlay.set_level(v))

        def work():
            try:
                text = svc.listen_once(level_callback=level)
            except VoiceCancelled:
                text = ""
            except Exception as exc:
                if chat.winfo_exists():
                    chat.after(0, lambda e=exc: chat.voice_failed(str(e)))
                return
            finally:
                chat._cloud_voice_listening = False

            if not text or not getattr(chat, "_cloud_voice_live", False):
                return
            if chat.winfo_exists():
                def send_text():
                    overlay.set_state(
                        self.t("فهمتك…", "Got it…"),
                        self.t("جاري تجهيز الرد", "Preparing the reply"),
                    )
                    overlay.set_level(0.12)
                    chat._voice_turn_started = True
                    chat.prefill_and_send(text)
                chat.after(0, send_text)

        threading.Thread(target=work, daemon=True, name="yaa-cloud-voice-listen").start()

    App.show_main = show_main
    App._show_splash = _show_splash
    App._voice_request = _voice_request
    App._yaa_cloud_v240_voice = True


def apply_cloud_voice_v240() -> None:
    global _APPLIED
    if _APPLIED:
        return
    _patch_facebook_routing()
    _patch_chat_ui()
    _patch_app_voice()
    _APPLIED = True
