"""v2.6: cancellable request isolation, safe Facebook routing and GitHub Desktop access.

This is deliberately a thin compatibility layer on top of v2.5; no cloud
credentials, browser automation or publishing permissions are added.
"""
from __future__ import annotations

import os
import queue
import re
import shutil
import subprocess
import threading
from pathlib import Path
from tkinter import ttk

_CANCEL = threading.local()
_INSTALLED = False


class TurnCancelled(BaseException):
    """Abandon a superseded request without showing an obsolete reply."""


def _check_cancel():
    ev = getattr(_CANCEL, 'event', None)
    if ev is not None and ev.is_set():
        raise TurnCancelled()


def open_github_desktop():
    """Open an existing local GitHub Desktop installation; never run shell text."""
    if os.name != 'nt':
        return False, 'تشغيل GitHub Desktop من داخل البرنامج متاح على Windows فقط.'
    local = Path(os.environ.get('LOCALAPPDATA', ''))
    roaming = Path(os.environ.get('APPDATA', ''))
    root = local / 'GitHubDesktop'
    candidates = [
        root / 'GitHubDesktop.exe',
        local / 'Programs' / 'GitHub Desktop' / 'GitHubDesktop.exe',
    ]
    if root.is_dir():
        candidates += sorted(root.glob('app-*/GitHubDesktop.exe'), reverse=True)
    # Do not execute untrusted PATH matches or arbitrary user-supplied commands.
    exe = next((p for p in candidates if p.is_file()), None)
    if exe:
        try:
            subprocess.Popen([str(exe)], stdin=subprocess.DEVNULL,
                             stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
                             creationflags=getattr(subprocess, 'CREATE_NO_WINDOW', 0))
            return True, 'فتحت GitHub Desktop ✅. إذا طلب تسجيل الدخول، اعمله بنفسك داخل GitHub Desktop.'
        except OSError:
            pass
    shortcut = roaming / 'Microsoft' / 'Windows' / 'Start Menu' / 'Programs' / 'GitHub Desktop.lnk'
    if shortcut.is_file():
        try:
            os.startfile(str(shortcut))
            return True, 'فتحت اختصار GitHub Desktop ✅.'
        except OSError:
            pass
    return False, ('GitHub Desktop مش ظاهر كبرنامج مثبت على جهازك. نزّله من '
                   'https://desktop.github.com/ ثم سجّل الدخول؛ ما في داعي ترسل أي كلمة سر للمساعد.')


def explicit_github_intent(text):
    s = ' '.join(str(text or '').split()).lower()
    return bool(re.search(r'(?:افتح|شغل|شغّل|open|launch|start)\s+(?:لي\s+)?(?:برنامج\s+)?(?:جيت\s*هاب|github)(?:\s+ديسكتوب|\s+desktop)?\s*[.!؟]?$', s))



def local_github_status():
    """Read-only local repo status using installed Git/GitHub Desktop Git."""
    repo = Path.home() / 'Desktop' / 'YourAssistantAgent'
    if not (repo / '.git').exists():
        return 'مش لاقي مستودع YourAssistantAgent على سطح المكتب. هذا فحص محلي، مش اتصال بحساب GitHub.'
    git = shutil.which('git')
    if not git and os.name == 'nt':
        root = Path(os.environ.get('LOCALAPPDATA', '')) / 'GitHubDesktop'
        candidates = sorted(root.glob('app-*/resources/app/git/cmd/git.exe'), reverse=True) if root.is_dir() else []
        git = str(next((x for x in candidates if x.is_file()), '')) or None
    if not git:
        return 'ما لقيت Git CLI على ويندوز. افتح GitHub Desktop لمراجعة حالة المستودع يدويًا.'
    try:
        result = subprocess.run([str(git), '-C', str(repo), 'status', '--porcelain=v1', '--branch'],
                                capture_output=True, text=True, encoding='utf-8', errors='replace',
                                timeout=6, creationflags=getattr(subprocess, 'CREATE_NO_WINDOW', 0))
    except (OSError, subprocess.TimeoutExpired):
        return 'قراءة حالة Git استغرقت أكثر من المسموح؛ ما غيرت أي ملف.'
    if result.returncode != 0:
        return 'ما قدرت أقرأ حالة المستودع محليًا. افتحه من GitHub Desktop للتأكد.'
    lines = [line for line in result.stdout.splitlines() if line.strip()]
    branch = lines[0][3:][:140] if lines and lines[0].startswith('## ') else 'غير معروف'
    dirty = sum(1 for line in lines if not line.startswith('## '))
    return f'المستودع المحلي: {branch}. عدد الملفات المتغيرة: {dirty}. ما عملت Commit أو Push.'


def explicit_git_status_intent(text):
    s = ' '.join(str(text or '').split()).lower()
    return bool(re.search(r'(?:افحص|شوف|تحقق|حالة|status|check).{0,20}(?:github|جيت\s*هاب|git\b|المستودع)', s))

def facebook_page_ambiguous(text):
    """Unsupported page editing: ask which action, never guess Photos/Stories."""
    s = ' '.join(str(text or '').split()).lower()
    has_page = bool(re.search(r'(?:صفحت[يها]?|صفحة|page|البيدج)', s))
    possible_edit = bool(re.search(r'(?:هايلايت|هايلات|highlight|ستلايت|الستلايت|story|ستوري|تثبيت|ثبّت|بين|pin|غلاف|بوست|منشور|إعلان|اعلان|الاعلان|الإعلان)', s))
    explicit_action = bool(re.search(r'(?:سو[يّ]|اعمل|اعملي|خلّي|حط|عدّل|ثبت|انشر|نزّل|create|make|pin|post)', s))
    return has_page and possible_edit and explicit_action


def should_discard_pending(text):
    """Unrelated new commands supersede old campaign approvals, never approve."""
    t = ' '.join(str(text or '').strip().split()).lower()
    if re.fullmatch(r'(?:نعم|موافق|اعتمد|أكد|تمام|yes|approve|confirm|لا|إلغاء|الغاء|cancel)\s*[.!؟]?', t):
        return False
    if re.search(r'(?:غيّر|غير|عدّل|عدل|بدل|استثن|زود|نقص|نفس|الخطة|المهمة السابقة|الوقت|الساعة)', t):
        return False
    return bool(re.match(r'(?:افتح|فحص|افحص|حدث|حدّث|شغل|شغّل|سوي|سوّي|اعمل|انشر|ارسل|ابحث|كيف|شو|ما|hello|hi|open|start|check|refresh)(?:\b|لي|له|ها)', t))


def _install_controller_safety():
    from .agent.orchestrator import AgentResponse, SmartAgentController
    from .agent.tools import ToolExecution, ToolRegistry
    from .fast_live_v250 import fast_refresh_groups, fast_check_facebook, fast_open_facebook
    from . import personal_assistant_v220 as pa
    if getattr(SmartAgentController, '_yaa_v260_safe', False):
        return

    # The model never receives a login-opening tool. A login screen can still be
    # opened on explicit user request, but not from guesses about page content.
    original_schemas = pa._tool_schemas
    def schemas_without_auto_login():
        return [x for x in original_schemas()
                if (x.get('function') or {}).get('name') != 'open_facebook_login']
    pa._tool_schemas = schemas_without_auto_login

    original_execute = ToolRegistry.execute
    def execute(self, name, arguments=None):
        _check_cancel()
        if name in {'verify_facebook_connection', 'facebook_status'}:
            fb = getattr(self, '_yaa_facebook', None)
            if fb is not None:
                msg = fast_check_facebook(fb)
                confirmed = msg.startswith('Facebook متصل ✅')
                return ToolExecution(confirmed, msg, {'verified': confirmed})
        if name == 'discover_facebook_groups':
            fb = getattr(self, '_yaa_facebook', None)
            if fb is not None:
                ok, msg, n = fast_refresh_groups(fb)
                return ToolExecution(ok, msg, {'count': n})
        outcome = original_execute(self, name, arguments)
        _check_cancel()
        return outcome
    ToolRegistry.execute = execute

    original_handle = SmartAgentController.handle
    def handle(self, profile, history, user_text, session_id, max_tokens, timeout, status=None):
        _check_cancel()
        s = str(user_text or '').strip()
        if explicit_git_status_intent(s):
            return AgentResponse(local_github_status(), used_model=False, used_tools=True, detail='local_git_status')
        if explicit_github_intent(s):
            try:
                if self.db.get_pending_action(session_id):
                    self.db.clear_pending_action(session_id)
            except Exception:
                pass
            _ok, msg = open_github_desktop()
            return AgentResponse(msg, used_model=False, used_tools=True, detail='github_desktop_launch')
        if facebook_page_ambiguous(s):
            try:
                if self.db.get_pending_action(session_id):
                    self.db.clear_pending_action(session_id)
            except Exception:
                pass
            return AgentResponse(
                'فهمت إنك بدك تعدّل شيئًا على صفحة فيسبوك، لكن طلبك مش محدد بما يكفي. '
                'هل تقصد تثبيت منشور، إنشاء ستوري/هايلايت، أو تجهيز إعلان؟ '
                'ابعث رابط الصفحة وحدد المطلوب. ما رح أفتح الصور أو أنشر من عندي.',
                used_model=False, used_tools=False, detail='facebook_page_needs_clarification')
        try:
            pending = self.db.get_pending_action(session_id)
            if pending and should_discard_pending(s):
                self.db.clear_pending_action(session_id)
        except Exception:
            pass
        # Keep text responses bounded during live voice. The user can ask for a
        # long explanation in text chat when desired.
        _check_cancel()
        answer = original_handle(self, profile, history, user_text, session_id,
                                 max_tokens, timeout, status=status)
        _check_cancel()
        return answer
    SmartAgentController.handle = handle
    SmartAgentController._yaa_v260_safe = True


def _install_runtime_cancellation():
    from .ai.runtime import LocalAIRuntime
    if getattr(LocalAIRuntime, '_yaa_v260_cancel', False):
        return
    old_native = LocalAIRuntime.native_turn
    def native(self, profile, messages, tools, max_tokens, timeout, status=None):
        _check_cancel()
        def monitored_status(value):
            _check_cancel()
            if status:
                status(value)
        result = old_native(self, profile, messages, tools, max_tokens, timeout,
                            status=monitored_status if status else None)
        _check_cancel()
        return result
    LocalAIRuntime.native_turn = native
    LocalAIRuntime._yaa_v260_cancel = True


def _install_request_isolation():
    from .ui.chat_window import ChatWindow
    if getattr(ChatWindow, '_yaa_v260_isolated', False):
        return
    old_build = ChatWindow._build
    old_poll = ChatWindow._poll_results
    old_destroy = ChatWindow.destroy
    old_prefill = ChatWindow.prefill_and_send

    def _cancel(self, *, quiet=False):
        active = getattr(self, '_v260_cancel_event', None)
        if active is not None:
            active.set()
        self._v260_serial = getattr(self, '_v260_serial', 0) + 1
        self._v260_cancel_event = None
        if not quiet:
            try:
                if self.db.get_pending_action(self.session_id):
                    self.db.clear_pending_action(self.session_id)
            except Exception:
                pass
        if not quiet and getattr(self, '_fast_voice_mode', ''):
            try:
                self._stop_fast_voice()
            except Exception:
                pass
        if getattr(self, '_fast_stream_active', False):
            try:
                self.chat.configure(state='normal')
                self.chat.delete('__yaa_stream_start', 'end-1c')
                self.chat.configure(state='disabled')
                self._fast_stream_active = False
            except Exception:
                pass
        self.busy = False
        try:
            self.send_btn.state(['!disabled'])
            if not quiet:
                self.status.config(text=self.t('أوقفت الطلب القديم. تقدر ترسل طلب جديد.',
                                               'Old request cancelled. Ready for a new one.'))
        except Exception:
            pass

    def _build(self):
        old_build(self)
        self._v260_serial = 0
        self._v260_cancel_event = None
        composer = self.input.master
        ttk.Button(composer, text='GitHub Desktop', command=lambda: self._v260_open_github()).grid(
            row=3, column=0, columnspan=2, sticky='w', padx=8, pady=(0, 8))
        ttk.Button(composer, text=self.t('حالة Git', 'Git status'),
                   command=lambda: self._v260_show_git()).grid(
                       row=3, column=2, columnspan=2, sticky='e', padx=8, pady=(0, 8))
        # Rebind the old "Stop Qwen" action, which was no longer cancelling a
        # cloud request; leaving it wired to runtime.stop() was misleading.
        for child in composer.winfo_children():
            try:
                text = str(child.cget('text'))
                if ('Stop GroqCloud' in text or 'Stop Qwen' in text or
                        'إيقاف GroqCloud' in text or 'إيقاف Qwen' in text):
                    child.configure(command=lambda: self._v260_cancel(quiet=False))
            except Exception:
                pass

    def _open_github(self):
        ok, msg = open_github_desktop()
        self.status.config(text=msg[:150])
        self._append('assistant', msg)
        return ok

    def _show_git(self):
        msg = local_github_status()
        self._append('assistant', msg)
        self.status.config(text=msg[:130])

    def _prefill(self, text):
        self._v260_voice_internal = True
        try:
            return old_prefill(self, text)
        finally:
            self._v260_voice_internal = False

    def send(self):
        text = self.input.get('1.0', 'end-1c').strip()
        if not text:
            return
        if getattr(self, '_fast_voice_mode', '') and not getattr(self, '_v260_voice_internal', False):
            try:
                self._stop_fast_voice()
            except Exception:
                pass
        if getattr(self, '_v260_cancel_event', None) is not None:
            self._v260_cancel(quiet=True)
        self._v260_serial = getattr(self, '_v260_serial', 0) + 1
        serial = self._v260_serial
        cancel_event = threading.Event()
        self._v260_cancel_event = cancel_event
        attachments = list(self.attachments)
        names = ', '.join(Path(p).name for p in attachments)
        text_for_ai = f'{text}\n\nAttached task files: {names}' if names else text
        self.input.delete('1.0', 'end')
        self._append('user', text)
        self.db.add_message('user', text, 'hammer', self.session_id)
        self.db.rename_session_from_first_message(self.session_id, text)
        if self.on_session_title_changed:
            self.on_session_title_changed()
        self.db.add_activity('chat_request', f'session={self.session_id}; {text[:400]}')
        history = self.db.recent_messages('hammer', 10, session_id=self.session_id)
        self.busy = True
        self.send_btn.state(['disabled'])
        self.status.config(text=self.t('جاري معالجة طلبك…', 'Processing your request…'))
        self.detail_btn.pack_forget()
        self.detail_box.pack_forget()

        def put(kind, value):
            if not cancel_event.is_set():
                self.result_q.put((kind, serial, value))
        def work():
            _CANCEL.event = cancel_event
            try:
                response = self.controller.handle(
                    self.profile, history[:-1], text_for_ai, self.session_id,
                    (480 if getattr(self, "_fast_voice_mode", "") == "live" else self.settings.max_response_tokens),
                    (25 if getattr(self, "_fast_voice_mode", "") == "live" else self.settings.ai_timeout_seconds),
                    status=lambda message: put('status', message))
                _check_cancel()
                put('reply', response)
            except TurnCancelled:
                pass
            except Exception as exc:
                put('ai_error', f'{type(exc).__name__}: {exc}')
            finally:
                _CANCEL.event = None
        threading.Thread(target=work, daemon=True, name=f'yaa-turn-{serial}').start()

    def _poll(self):
        # Drop all statuses and replies from superseded turns, including
        # streamed previews and late tool results. Never replay them in a chat.
        kept = []
        try:
            while True:
                item = self.result_q.get_nowait()
                if len(item) == 3:
                    kind, serial, value = item
                    if serial == getattr(self, '_v260_serial', -1):
                        kept.append((kind, value))
                elif len(item) == 2:
                    kept.append(item)
        except queue.Empty:
            pass
        for item in kept:
            self.result_q.put(item)
        if any(kind in {'reply', 'ai_error'} for kind, _ in kept):
            self._v260_cancel_event = None
        if any(kind == 'ai_error' for kind, _ in kept) and getattr(self, '_fast_voice_mode', '') == 'live':
            self._fast_voice_events.put(('listen_error', self._fast_voice_generation,
                'تعذر تنفيذ الطلب الصوتي، وتم إيقاف الاستماع حتى لا يظل معلقًا. راجع تفاصيل الخطأ.'))
        return old_poll(self)

    def _destroy(self):
        self._v260_cancel(quiet=True)
        try:
            svc = getattr(self, '_fast_listen_service', None)
            if svc: svc.cancel()
            svc = getattr(self, '_fast_tts_service', None)
            if svc: svc.cancel()
            overlay = getattr(self, '_cloud_voice_overlay', None)
            if overlay: overlay.close()
        except Exception:
            pass
        return old_destroy(self)

    ChatWindow._build = _build
    ChatWindow.send = send
    ChatWindow.prefill_and_send = _prefill
    ChatWindow._poll_results = _poll
    ChatWindow._v260_cancel = _cancel
    ChatWindow._v260_open_github = _open_github
    ChatWindow._v260_show_git = _show_git
    ChatWindow.stop_ai = lambda self: self._v260_cancel(quiet=False)
    ChatWindow.destroy = _destroy
    ChatWindow._yaa_v260_isolated = True


def _install_voice_recovery():
    from .ui.app import App
    from .ui.chat_window import ChatWindow
    from .voice.cloud_service import CloudVoiceService, VoiceCancelled
    from .cloud_voice_v240 import _ensure_overlay
    if getattr(App, '_yaa_v260_voice', False):
        return
    def voice_request(self, chat):
        mode = getattr(chat, '_fast_voice_mode', '')
        if not mode:
            return
        if not getattr(self.settings_obj, 'voice_enabled', True):
            chat._fast_voice_events.put(('listen_error', chat._fast_voice_generation,
                'الصوت غير مفعّل من الإعدادات. فعّله ثم جرّب.'))
            return
        if chat.busy or getattr(chat, '_cloud_voice_listening', False):
            return
        gen = chat._fast_voice_generation
        svc = CloudVoiceService(self.settings_obj)  # NEVER share STT/TTS cancel state
        chat._fast_listen_service = svc
        chat._cloud_voice_listening = True
        overlay = _ensure_overlay(chat)
        overlay.set_state('أسمعك… احكي بصوت واضح', 'بتشوف الموجات تتحرك، ولما تسكت رح أحوّل صوتك إلى كلام')
        chat.status.config(text='🎙 الميكروفون شغال…')
        def work():
            try:
                text = svc.listen_once(mode=mode, level_callback=lambda level:
                    chat._fast_voice_events.put(('level', gen, level)))
                if not svc.cancel_event.is_set() and text.strip():
                    chat._fast_voice_events.put(('heard', gen, text))
            except VoiceCancelled:
                pass
            except Exception as exc:
                chat._fast_voice_events.put(('listen_error', gen,
                    f'الميكروفون/فهم العربي تعطل: {type(exc).__name__}: {str(exc)[:140]}'))
            finally:
                chat._cloud_voice_listening = False
        threading.Thread(target=work, daemon=True, name='yaa-v260-voice-listen').start()

    old_stop = ChatWindow._stop_fast_voice
    def stop_voice(self):
        try:
            svc = getattr(self, '_fast_listen_service', None)
            if svc: svc.cancel()
            svc = getattr(self, '_fast_tts_service', None)
            if svc: svc.cancel()
        except Exception:
            pass
        return old_stop(self)

    old_speak = ChatWindow._maybe_speak_reply
    def speak_after_reply(self, text):
        mode = getattr(self, '_fast_voice_mode', '')
        if mode != 'live' or not getattr(self, '_cloud_voice_live', False):
            return old_speak(self, text)  # honour configured text-chat voice behaviour
        gen = self._fast_voice_generation
        # Live replies are intentionally concise to reduce voice latency.
        spoken = ' '.join(str(text or '').split()).strip()[:190]
        if not spoken:
            self._fast_voice_events.put(('listen_error', gen, 'الرد كان فارغًا؛ جرّب مرة ثانية.'))
            return
        svc = CloudVoiceService(self.settings)
        self._fast_tts_service = svc
        overlay = _ensure_overlay(self)
        overlay.set_state('نورا بتجهّز الرد الصوتي…', 'الرد النصي ظاهر فوق، وراح يبدأ الصوت بمجرد ما يجهز')
        self.status.config(text='🔊 جاري تجهيز صوت نورا…')
        def work():
            try:
                provider = svc.speak(spoken)
                if provider == 'windows':
                    self._fast_voice_events.put(('voice_fallback', gen, 'Noura غير متاحة مؤقتًا؛ استُخدم الصوت العربي المحلي إن وجد.'))
            except VoiceCancelled:
                return
            except Exception as exc:
                self._fast_voice_events.put(('listen_error', gen,
                    f'ما قدرت أشغّل صوت نورا: {type(exc).__name__}: {str(exc)[:100]}'))
                return
            self._fast_voice_events.put(('tts_done', gen, None))
        threading.Thread(target=work, daemon=True, name='yaa-v260-noura').start()

    App._voice_request = voice_request
    ChatWindow._stop_fast_voice = stop_voice
    ChatWindow._maybe_speak_reply = speak_after_reply
    App._yaa_v260_voice = True


def apply_stability_v260():
    global _INSTALLED
    if _INSTALLED:
        return
    _install_runtime_cancellation()
    _install_controller_safety()
    _install_request_isolation()
    _install_voice_recovery()
    _INSTALLED = True
