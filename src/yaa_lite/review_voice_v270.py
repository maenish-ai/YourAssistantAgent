"""v2.7: explicit local approval UI and optional Arabic female voice comparison.

No general command execution, phone API, credential upload or payment path is added.
A desktop *click* is required to authorize each existing mutating agent tool.
"""
from __future__ import annotations

import hashlib
import json
import queue
import re
import threading
import time
from datetime import datetime, timezone
from tkinter import ttk, messagebox

from .voice.provider_v270 import (
    get_voice_preference, set_voice_preference, speak_with_provider,
    PUBLIC_PREVIEW_TEXT, redact_sensitive_text,
)

_ALLOWED_MUTATIONS = frozenset({
    'approve_facebook_campaign', 'run_facebook_rule_now',
})
_READ_ONLY_TOOLS = frozenset({
    'app_status', 'facebook_status', 'verify_facebook_connection',
    'discover_facebook_groups', 'search_facebook_groups',
    'list_tasks', 'backup_status', 'count_facebook_groups',
})
_APPROVAL_TTL_SECONDS = 15 * 60
_CLICK_TTL_SECONDS = 45
_CONFIRM = re.compile(r'^\s*(?:نعم|موافق|اعتمد|اكد|أكد|تمام|yes|approve|confirm)\s*[.!؟]?\s*$', re.I)
_LOCAL_APPROVAL = threading.local()
_INSTALLED = False


def pending_signature(pending: dict | None) -> str:
    if not pending:
        return ''
    payload = {
        'tool_name': str(pending.get('tool_name') or ''),
        'arguments': pending.get('arguments') or {},
        'summary': str(pending.get('summary') or ''),
        'created_at': str(pending.get('created_at') or ''),
    }
    data = json.dumps(payload, sort_keys=True, ensure_ascii=False, separators=(',', ':'), default=str)
    return hashlib.sha256(data.encode('utf-8')).hexdigest()


def pending_is_fresh(pending: dict | None, now: datetime | None = None) -> bool:
    if not pending or pending.get('tool_name') not in _ALLOWED_MUTATIONS:
        return False
    try:
        raw = str(pending.get('created_at') or '')
        created = datetime.fromisoformat(raw.replace('Z', '+00:00'))
        if created.tzinfo is None:
            # SQLite CURRENT_TIMESTAMP is UTC.
            created = created.replace(tzinfo=timezone.utc)
        moment = now or datetime.now(timezone.utc)
        seconds = (moment - created).total_seconds()
        return 0 <= seconds <= _APPROVAL_TTL_SECONDS
    except (ValueError, TypeError):
        return False


def permitted_mutation(tool_name: str, arguments: dict | None = None) -> bool:
    """Never let model-controlled tool arguments grant their own permission."""
    if tool_name in _READ_ONLY_TOOLS:
        return True
    # Deny by default: newly introduced or unknown tools have no execution
    # rights until explicitly classified and reviewed in this boundary.
    approval = getattr(_LOCAL_APPROVAL, 'details', None)
    if not approval or tool_name not in _ALLOWED_MUTATIONS:
        return False
    return (approval['tool'] == tool_name
            and approval['arguments'] == json.dumps(arguments or {}, sort_keys=True,
                                                     ensure_ascii=False, separators=(',', ':'), default=str)
            and time.monotonic() <= approval['deadline'])


def install_execution_boundary():
    from .agent.tools import ToolExecution, ToolRegistry
    from .agent.orchestrator import AgentResponse, SmartAgentController
    if getattr(ToolRegistry, '_yaa_v270_mutation_guard', False):
        return

    old_execute = ToolRegistry.execute
    def execute(self, name, arguments=None):
        if not permitted_mutation(name, arguments):
            return ToolExecution(False, 'BLOCKED: هذا إجراء حساس يحتاج موافقة صريحة من زر «موافق» على تفاصيل هذه العملية.')
        return old_execute(self, name, arguments)
    ToolRegistry.execute = execute
    ToolRegistry._yaa_v270_mutation_guard = True

    old_handle = SmartAgentController.handle
    def handle(self, profile, history, user_text, session_id, max_tokens, timeout, status=None):
        text = str(user_text or '').strip()
        if not _CONFIRM.fullmatch(text):
            self._v270_authorization = None
            return old_handle(self, profile, history, user_text, session_id, max_tokens, timeout, status=status)
        pending = self.db.get_pending_action(session_id)
        if not pending:
            return old_handle(self, profile, history, user_text, session_id, max_tokens, timeout, status=status)
        if not pending_is_fresh(pending):
            self.db.clear_pending_action(session_id)
            return AgentResponse('انتهت صلاحية طلب الموافقة. اطلب تجهيز العملية من جديد قبل التنفيذ.', used_tools=False)
        authorization = getattr(self, '_v270_authorization', None)
        # In-memory authorization is produced only by clicking the local button.
        self._v270_authorization = None  # single use
        if not authorization or authorization[0] != pending_signature(pending) or time.monotonic() > authorization[1]:
            return AgentResponse('لأمان حساباتك، لازم تضغط زر «موافق» الظاهر مع تفاصيل العملية. كلمة «نعم» وحدها لا تنفّذها.', used_tools=False)
        _LOCAL_APPROVAL.details = {
            'tool': pending['tool_name'],
            'arguments': json.dumps(pending.get('arguments') or {}, sort_keys=True,
                                    ensure_ascii=False, separators=(',', ':'), default=str),
            'deadline': time.monotonic() + _CLICK_TTL_SECONDS,
        }
        try:
            return old_handle(self, profile, history, user_text, session_id, max_tokens, timeout, status=status)
        finally:
            _LOCAL_APPROVAL.details = None
    SmartAgentController.handle = handle
    SmartAgentController._yaa_v270_local_approvals = True


def install_voice_and_approval_ui():
    from .ui.chat_window import ChatWindow
    from .voice.cloud_service import CloudVoiceService
    if getattr(ChatWindow, '_yaa_v270_voice_review', False):
        return

    old_speak = CloudVoiceService.speak
    def speak(self, text):
        safe_text = redact_sensitive_text(str(text or ''))
        if get_voice_preference() == 'sana':
            return speak_with_provider('sana', safe_text, self.cancel_event)
        return old_speak(self, safe_text)
    CloudVoiceService.speak = speak

    old_build = ChatWindow._build
    old_poll = ChatWindow._poll_results
    old_destroy = ChatWindow.destroy
    old_cancel = ChatWindow._v260_cancel

    def _build(self):
        old_build(self)
        self._v270_voice_events = queue.Queue()
        self._v270_preview_service = None
        self._v270_preview_cancel = None
        self._v270_preview_serial = 0
        self._v270_last_review = ''
        self._v270_review_frame = ttk.Frame(self, padding=(16, 8))
        self._v270_review_title = ttk.Label(self._v270_review_frame, text='🔐 هذه العملية تنتظر موافقتك',
                                            style='CardTitle.TLabel')
        self._v270_review_title.pack(anchor='w')
        self._v270_review_text = ttk.Label(self._v270_review_frame, text='', wraplength=770, justify='right')
        self._v270_review_text.pack(fill='x', pady=5)
        actions = ttk.Frame(self._v270_review_frame)
        actions.pack(fill='x', pady=3)
        self._v270_approve_button = ttk.Button(actions, text='✅ موافق — نفّذ العملية المعروضة',
                                                command=self._v270_approve)
        self._v270_approve_button.pack(side='right', padx=4)
        ttk.Button(actions, text='✖ إلغاء', command=self._v270_reject).pack(side='right', padx=4)
        self._v270_review_frame.grid(row=4, column=0, sticky='ew', padx=16, pady=4)
        self._v270_review_frame.grid_remove()

        composer = self.input.master
        choice = ttk.Frame(composer)
        choice.grid(row=4, column=0, columnspan=5, sticky='ew', padx=8, pady=(0, 7))
        ttk.Label(choice, text='صوت المساعدة:').pack(side='left', padx=(0, 5))
        self._v270_voice_selection = __import__('tkinter').StringVar(value=get_voice_preference())
        ttk.Radiobutton(choice, text='Noura (Groq)', value='noura',
                        variable=self._v270_voice_selection, command=self._v270_select_voice).pack(side='left', padx=4)
        ttk.Radiobutton(choice, text='Sana (تجريبي)', value='sana',
                        variable=self._v270_voice_selection, command=self._v270_select_voice).pack(side='left', padx=4)
        ttk.Button(choice, text='🔊 جرّب الصوت', command=self._v270_preview).pack(side='right')

    def _v270_select_voice(self):
        choice = self._v270_voice_selection.get()
        if choice == 'sana' and not messagebox.askyesno(
                'Sana — خدمة خارجية تجريبية',
                'هذا الصوت يستخدم edge-tts غير الرسمي. النصوص المنطوقة تُرسل إلى Microsoft، وليس إلى Groq فقط.\n\n'
                'هل توافق على ذلك؟ لا ترسل محتوى سريًا عبر هذا الصوت.', parent=self):
            self._v270_voice_selection.set('noura')
            set_voice_preference('noura')
            return
        try:
            set_voice_preference(choice)
            if choice == 'sana':
                self.status.config(text='Sana عبر خدمة Microsoft غير الرسمية؛ لا ترسل معلومات سرية للصوت.')
            else:
                self.status.config(text='اخترت Noura عبر GroqCloud.')
        except Exception as exc:
            self.status.config(text=f'تعذر حفظ الصوت: {type(exc).__name__}')

    def _v270_preview(self):
        provider = self._v270_voice_selection.get()
        try:
            set_voice_preference(provider)
        except Exception as exc:
            self.status.config(text=f'خطأ بالإعدادات: {exc}')
            return
        old_cancel = getattr(self, '_v270_preview_cancel', None)
        if old_cancel:
            old_cancel.set()
        cancel = threading.Event()
        self._v270_preview_cancel = cancel
        self._v270_preview_serial += 1
        serial = self._v270_preview_serial
        self.status.config(text=f'جاري تجربة {provider}…')
        def work():
            try:
                if provider == 'noura':
                    service = CloudVoiceService(self.settings)
                    self._v270_preview_service = service
                    # Use the explicit Groq voice, independent of selected-provider patch.
                    if not service._speak_cloud_arabic(PUBLIC_PREVIEW_TEXT):
                        raise RuntimeError('Groq Noura unavailable (network/free tier).')
                else:
                    speak_with_provider('sana', PUBLIC_PREVIEW_TEXT, cancel)
                message = f'✅ تشغيل {provider} نجح على جهازك.'
            except Exception as exc:
                message = f'تعذر تجربة {provider}: {type(exc).__name__}: {str(exc)[:110]}'
            if not cancel.is_set():
                self._v270_voice_events.put((serial, message))
        threading.Thread(target=work, daemon=True, name=f'yaa-v270-preview-{serial}').start()

    def _v270_approve(self):
        pending = self.db.get_pending_action(self.session_id)
        if self.busy or not pending or not pending_is_fresh(pending):
            self.status.config(text='الموافقة غير صالحة أو العملية قيد التنفيذ. اطلب تجهيز العملية مجددًا.')
            return
        if pending_signature(pending) != self._v270_last_review:
            self.status.config(text='تفاصيل الطلب تغيّرت؛ راجع العملية الجديدة قبل الموافقة.')
            return
        self.controller._v270_authorization = (self._v270_last_review,
                                                time.monotonic() + _CLICK_TTL_SECONDS)
        self.prefill_and_send('نعم')

    def _v270_reject(self):
        if self.busy:
            return
        self.controller._v270_authorization = None
        self.prefill_and_send('إلغاء')

    def _poll(self):
        result = old_poll(self)
        try:
            while True:
                serial, msg = self._v270_voice_events.get_nowait()
                if serial == self._v270_preview_serial:
                    self.status.config(text=msg)
        except queue.Empty:
            pass
        try:
            pending = self.db.get_pending_action(self.session_id)
            signature = pending_signature(pending) if pending_is_fresh(pending) else ''
            if signature != self._v270_last_review:
                self._v270_last_review = signature
                if signature:
                    self._v270_review_text.config(text=str(pending.get('summary') or '')[:3000])
                    self._v270_review_frame.grid()
                else:
                    self._v270_review_frame.grid_remove()
            self._v270_approve_button.state(['disabled'] if self.busy else ['!disabled'])
        except Exception:
            pass
        return result

    def _cancel(self, *, quiet=False):
        if not quiet:
            self.controller._v270_authorization = None
        return old_cancel(self, quiet=quiet)

    def _destroy(self):
        if self._v270_preview_cancel:
            self._v270_preview_cancel.set()
        svc = getattr(self, '_v270_preview_service', None)
        if svc:
            svc.cancel()
        return old_destroy(self)

    ChatWindow._build = _build
    ChatWindow._poll_results = _poll
    ChatWindow._v270_approve = _v270_approve
    ChatWindow._v270_reject = _v270_reject
    ChatWindow._v270_select_voice = _v270_select_voice
    ChatWindow._v270_preview = _v270_preview
    ChatWindow._v260_cancel = _cancel
    ChatWindow.destroy = _destroy
    ChatWindow._yaa_v270_voice_review = True


def apply_review_voice_v270():
    global _INSTALLED
    if _INSTALLED:
        return
    install_execution_boundary()
    install_voice_and_approval_ui()
    _INSTALLED = True
