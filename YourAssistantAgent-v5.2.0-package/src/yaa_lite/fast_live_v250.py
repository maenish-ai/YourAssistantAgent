"""v2.5 fast paths and two-mode cloud voice on top of the v2.4 compatibility layer.

The browser and microphone remain on the user's computer. This file adds no
paid service, no credential storage, and no hidden publishing capability.
"""
from __future__ import annotations

import json
import queue
import re
import threading
import webbrowser
from tkinter import ttk

from .voice.cloud_service import CloudVoiceService, VoiceCancelled
from .agent.intent import normalized_command,explicit_example_only

_INSTALLED = False
_STREAM_PREFIX = "__YAA_STREAM_V250__:"

_FB_OPEN = re.compile(r"^\s*(?:افتح(?:لي)?|فتح|شغل|فوت(?:ني)?|ادخل(?:ني)?|وديني|روح|open|launch)\s+(?:لي\s+)?(?:(?:متصفح|المتصفح|براوزر|البراوزر|browser)\s+(?:على\s+|ع\s*)?)?(?:على\s+|ع\s*)?(?:ال)?(?:فيس\s*بوك|فيسبوك|facebook)(?:\s+عندي|\s+الان|\s+now)?\s*[.!؟]?$", re.I)
_FB_REFRESH = re.compile(r"^\s*(?:حدث|حدّث|تحديث|جدد|جدّد|تعرف على|تعرّف على|اكتشف|جيب لي|شوف لي|refresh|update|discover|زامن)\s+(?:قائمة\s+)?(?:ال)?(?:مجموعات|جروبات|groups)(?:\s+(?:الفيس\s*بوك|فيسبوك|facebook|عندي))?(?:\s+(?:الآن|now))?\s*[.!؟]?$", re.I)
_FB_CHECK = re.compile(r"(?:افحص|فحص|تحقق|شيك|تأكد|check|verify).{0,28}(?:فيس\s*بوك|فيسبوك|facebook)|(?:حالة|اتصال|status|connection).{0,20}(?:فيس\s*بوك|فيسبوك|facebook)", re.I)


def fast_facebook_intent(text: str) -> str | None:
    text = normalized_command(text)
    if explicit_example_only(text):return None
    # The dedicated publishing profile must not be checked/opened through the
    # normal extension connection by the generic Facebook fast path.
    if re.search(r'publishing|managed|النشر|المُدار|المدار', text, re.I):
        return None
    if _FB_OPEN.fullmatch(text):
        return "open"
    # The remote and Windows paths share the same plain-navigation recognizer.
    # Browser/desktop wording must still open the managed Facebook session.
    from .remote.desktop_intent import direct_task
    direct = direct_task(text)
    if direct and direct[0] == 'open_url':
        from urllib.parse import urlsplit
        target = urlsplit(direct[1].get('url') or '')
        if target.hostname in {'facebook.com', 'www.facebook.com'} and target.path in {'','/'} and not target.query and not target.fragment:
            return "open"
    if _FB_REFRESH.fullmatch(text):
        return "refresh"
    if _FB_CHECK.search(text) and not re.search(r'منشور|بوست|اعلان|إعلان|جروب|مجموعات|صفحة|\bposts?\b|\bgroups?\b',text):
        return "check"
    return None


def _install_discovery_bridge() -> None:
    """Allow the existing extension's bounded discovery action; no generic exec."""
    from .browser_bridge.server import BrowserBridge
    if getattr(BrowserBridge, "_yaa_v250_groups", False):
        return
    # The core bridge owns allowlisting, normalization and command expiry.
    BrowserBridge._yaa_v250_groups = True


def fast_refresh_groups(fb, limit=120, deep=False):
    """Use the connected browser, falling back to the app controlled session on request."""
    result=fb.discover_groups(limit=limit,deep=deep)
    return result.ok,result.message,result.count


def fast_check_facebook(fb):
    result=fb.verify_session()
    if result.ok:return result.message
    opened=fb.open_manual_login()
    return result.message+'\n'+opened.message


def fast_open_facebook(fb):
    return fb.open_manual_login().message


def _install_facebook_fast_paths() -> None:
    from .agent.orchestrator import AgentResponse, SmartAgentController
    if getattr(SmartAgentController, "_yaa_v250_fast", False):
        return
    old_handle = SmartAgentController.handle

    def handle(self, profile, history, user_text, session_id, max_tokens, timeout, status=None):
        intent = fast_facebook_intent(user_text)
        if not intent:
            return old_handle(self, profile, history, user_text, session_id, max_tokens, timeout, status=status)
        fb = getattr(self.tools, "_yaa_facebook", None)
        if fb is None:
            return AgentResponse("Facebook غير جاهز داخل البرنامج.", used_tools=False)
        if status:
            status("Facebook • " + {"open":"opening", "check":"checking", "refresh":"refreshing"}[intent])
        if intent == "open":
            txt = fast_open_facebook(fb)
        elif intent == "check":
            txt = fast_check_facebook(fb)
        else:
            _ok, txt, _count = fast_refresh_groups(fb)
        return AgentResponse(txt, used_model=False, used_tools=True, detail=f"fast_facebook_{intent}")

    SmartAgentController.handle = handle
    SmartAgentController._yaa_v250_fast = True


def _install_voice_ui() -> None:
    from .ui.chat_window import ChatWindow
    from .ui.app import App
    from .cloud_voice_v240 import _ensure_overlay

    if getattr(ChatWindow, "_yaa_v250_voice", False):
        return
    old_build = ChatWindow._build
    old_poll = ChatWindow._poll_results
    old_maybe_speak = ChatWindow._maybe_speak_reply

    def _build(self):
        old_build(self)
        self._fast_voice_events = queue.Queue()
        self._fast_voice_mode = ""
        self._fast_voice_generation = 0
        self._fast_speaking = False
        self._fast_stream_active = False
        composer = self.input.master
        ttk.Button(composer, text=self.t("✍ إملاء إلى النص", "✍ Dictate to text"),
                   command=lambda: self._start_fast_voice("dictation")).grid(
                       row=2, column=0, columnspan=2, sticky="w", padx=8, pady=(0, 8))
        ttk.Button(composer, text=self.t("◉ محادثة صوتية", "◉ Live conversation"),
                   command=lambda: self._start_fast_voice("live")).grid(
                       row=2, column=2, columnspan=3, sticky="e", padx=8, pady=(0, 8))

    def _stop_fast_voice(self):
        self._fast_voice_generation += 1
        self._fast_voice_mode = ""
        self._cloud_voice_live = False
        self._cloud_voice_listening = False
        self._voice_turn_started = False
        svc = self._cloud_voice_service
        if svc:
            svc.cancel()
        overlay = getattr(self, "_cloud_voice_overlay", None)
        if overlay:
            overlay.close()
        self.status.config(text=self.t("أوقفت الميكروفون", "Microphone stopped"))

    def _start_fast_voice(self, mode):
        if self._fast_voice_mode:
            self._stop_fast_voice()
            return
        if self.busy:
            return
        self._fast_voice_mode = mode
        self._cloud_voice_live = (mode == "live")
        self._voice_turn_started = (mode == "live")
        self._fast_voice_generation += 1
        overlay = _ensure_overlay(self)
        overlay.stop_btn.configure(command=self._stop_fast_voice)
        overlay.set_state(self.t("أسمعك… احكي", "Listening… speak"),
                          self.t("إملاء: كلامك يصير كتابة" if mode == "dictation" else "محادثة: برد عليك صوتيًا",
                                 "Dictation: speech to text" if mode == "dictation" else "Live: I will speak back"))
        self.on_voice_request(self)

    def _voice(self):
        self._start_fast_voice("live")

    def _maybe_speak_reply(self, text):
        if getattr(self, "_fast_voice_mode", "") != "live":
            # Cloud v2.4 voice playback remains for explicit 'always' settings.
            return old_maybe_speak(self, text)
        self._voice_turn_started = False
        if not self._cloud_voice_live:
            return
        svc = self._cloud_voice_service
        if svc is None:
            svc = CloudVoiceService(self.settings)
            self._cloud_voice_service = svc
        gen = self._fast_voice_generation
        # A single short TTS request is much faster than reading an essay in chunks.
        phrase = " ".join(str(text or "").split())[:180]
        overlay = _ensure_overlay(self)
        overlay.set_state(self.t("نورا بتحكي…", "Noura is speaking…"),
                          self.t("اضغط إيقاف أو الميكروفون للمقاطعة", "Press stop or mic to interrupt"))

        def work():
            try:
                svc.reset_cancel()
                svc.speak(phrase)
            except VoiceCancelled:
                pass
            except Exception as exc:
                try:
                    self.db.add_activity("voice_error", f"{type(exc).__name__}: {exc}")
                except Exception:
                    pass
            finally:
                self._fast_voice_events.put(("tts_done", gen, None))

        threading.Thread(target=work, daemon=True, name="yaa-v250-noura").start()

    def _poll_results(self):
        events = getattr(self, "_fast_voice_events", None)
        if events:
            try:
                while True:
                    kind, gen, value = events.get_nowait()
                    if gen != self._fast_voice_generation:
                        continue
                    overlay = getattr(self, "_cloud_voice_overlay", None)
                    if kind == "level" and overlay:
                        overlay.set_level(float(value))
                    elif kind == "heard":
                        if self._fast_voice_mode == "dictation":
                            self.input.insert("insert", str(value))
                            self._fast_voice_mode = ""
                            self._cloud_voice_live = False
                            self._voice_turn_started = False
                            if overlay: overlay.close()
                            self.status.config(text=self.t("تمت الكتابة؛ راجع النص قبل الإرسال", "Dictated; review before sending"))
                        elif self._fast_voice_mode == "live":
                            if overlay: overlay.set_state(self.t("فهمت عليك…", "Got it…"), self.t("بجهز الرد", "Preparing reply"))
                            self._voice_turn_started = True
                            self.prefill_and_send(str(value))
                    elif kind == "voice_fallback":
                        self.status.config(text=str(value)[:170])
                    elif kind == "listen_error":
                        self._stop_fast_voice()
                        self.status.config(text=str(value)[:160])
                    elif kind == "tts_done" and self._fast_voice_mode == "live" and self._cloud_voice_live:
                        self.on_voice_request(self)
            except queue.Empty:
                pass

        # Show streamed model output as a disposable in-chat preview; final answer
        # is written by the original persistence path exactly once.
        pending = []
        chunks = []
        try:
            while True:
                kind, value = self.result_q.get_nowait()
                if kind == "status" and isinstance(value, str) and value.startswith(_STREAM_PREFIX):
                    chunks.append(value[len(_STREAM_PREFIX):])
                else:
                    pending.append((kind, value))
        except queue.Empty:
            pass
        if chunks:
            snippet = chunks[-1][-2000:]
            try:
                self.chat.configure(state="normal")
                if self._fast_stream_active:
                    self.chat.delete("__yaa_stream_start", "end-1c")
                else:
                    self.chat.mark_set("__yaa_stream_start", "end-1c")
                    self._fast_stream_active = True
                self.chat.insert("end", "\n" + snippet + "\n", "system_hint")
                self.chat.configure(state="disabled")
                self.chat.see("end")
            except Exception:
                pass
        if any(kind in {"reply", "ai_error"} for kind, _ in pending) and self._fast_stream_active:
            try:
                self.chat.configure(state="normal")
                self.chat.delete("__yaa_stream_start", "end-1c")
                self.chat.configure(state="disabled")
            except Exception:
                pass
            self._fast_stream_active = False
        for msg in pending:
            self.result_q.put(msg)
        return old_poll(self)

    def _voice_request(self, chat):
        if not self.settings_obj.voice_enabled:
            chat._stop_fast_voice()
            chat.status.config(text=self.t("فعّل الصوت من الإعدادات", "Enable voice in Settings"))
            return
        if getattr(chat, "_cloud_voice_listening", False) or not getattr(chat, "_fast_voice_mode", ""):
            return
        mode = chat._fast_voice_mode
        gen = chat._fast_voice_generation
        svc = getattr(chat, "_cloud_voice_service", None)
        if svc is None:
            svc = CloudVoiceService(self.settings_obj)
            chat._cloud_voice_service = svc
        else:
            svc.settings = self.settings_obj
        svc.reset_cancel()
        chat._cloud_voice_listening = True
        overlay = _ensure_overlay(chat)
        overlay.set_state(self.t("أسمعك… احكي", "Listening… speak"),
                          self.t("لما تسكت نص ثانية بفهم كلامك", "A short pause finishes your sentence"))

        def work():
            try:
                text = svc.listen_once(mode=mode,
                    level_callback=lambda level: chat._fast_voice_events.put(("level", gen, level)))
                if text:
                    chat._fast_voice_events.put(("heard", gen, text))
            except VoiceCancelled:
                pass
            except Exception as exc:
                chat._fast_voice_events.put(("listen_error", gen, str(exc)))
            finally:
                chat._cloud_voice_listening = False
        threading.Thread(target=work, daemon=True, name="yaa-v250-listen-" + mode).start()

    ChatWindow._build = _build
    ChatWindow._voice = _voice
    ChatWindow._start_fast_voice = _start_fast_voice
    ChatWindow._stop_fast_voice = _stop_fast_voice
    ChatWindow._maybe_speak_reply = _maybe_speak_reply
    ChatWindow._poll_results = _poll_results
    App._voice_request = _voice_request
    ChatWindow._yaa_v250_voice = True


def apply_fast_live_v250() -> None:
    global _INSTALLED
    if _INSTALLED:
        return
    _install_discovery_bridge()
    _install_facebook_fast_paths()
    _install_voice_ui()
    _INSTALLED = True
