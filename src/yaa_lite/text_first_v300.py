"""Text-first 3.0 chat shell for the Groq desktop client.

No microphone stream exists until Dictate is clicked; no speech playback occurs.
All Tk mutations stay on the main thread. Existing local action approval
policy remains enforced inside the controller, not solely by this UI.
"""
from __future__ import annotations

import queue
import re
import threading
import time
import tkinter as tk
from pathlib import Path
from tkinter import filedialog, ttk

from .agent.orchestrator import AgentResponse
from .ai.profiles import QWEN
from .ai.runtime import GROQ_MODEL
from .config import Settings
from .review_voice_v270 import pending_signature, pending_is_fresh
from .stability_v260 import _CANCEL, TurnCancelled, _check_cancel, local_github_status, open_github_desktop
from .ui import theme

# No TTS imports, no background microphone and no voice engine preloading.
REQUEST_DEADLINE_MS = 50_000
_STREAM_PREFIX = '__YAA_STREAM_V250__:'
_INSTALLED = False


def is_single_facebook_link(text: str) -> bool:
    return bool(re.fullmatch(r'https?://(?:www\.|m\.)?facebook\.com/[^\s<>]+', text.strip(), re.I))


def normalize_listen_text(text: str) -> str:
    return ' '.join(str(text or '').split()).strip()


def requires_local_tools(text: str) -> bool:
    """Fast path normal conversation without the expensive tool-planning loop.

    This is only a performance hint. Possible external actions always go through
    the existing explicit allowlist and owner approval boundary.
    """
    return bool(re.search(
        r'(?:افتح|شغّل|شغل|اضبط|احذف|حذف|امسح|ارفع|نزّل|انشر|ابعث|أرسل|ارسل|جدول|سوي|سوّي|اعمل|أعمل|افحص|فحص|عدل|عدّل|حدّث|حدث|'
        r'فيس\s?بوك|جروب|قروب|متصفح|تصفح|واتساب|تلغرام|تليجرام|جيت[ -]?هاب|github|\bgit\b|\brepo\b|'
        r'الملفات|المجلد|المهمة|المهام|الكمبيوتر|المجموعات|\bopen\b|\bupload\b|'
        r'\bdelete\b|\bpublish\b|\bdownload\b|\btask\b|\bfacebook\b|\bbrowser\b|\bgroups?\b|'
        r'\brefresh\b|\bverify\b|\bbackup\b|\bschedule\b|\bpost\b)',
        str(text or ''), re.I,
    ))


def chat_context(db, session_id: int, current_text: str) -> list[dict]:
    """Use bounded context from this chat when its memory is enabled.

    The current user message has already been persisted by send(); remove that
    one copy so the request adds it only once. Nothing from other chats is read.
    """
    session = db.get_session(session_id)
    if not session or not int(session.get('memory_enabled', 1)):
        return []
    rows = db.recent_messages('hammer', 13, session_id=session_id)
    if rows and rows[-1].get('role') == 'user' and rows[-1].get('content') == current_text:
        rows = rows[:-1]
    context = []
    remaining = 6000
    for row in reversed(rows[-12:]):
        role = row.get('role')
        content = str(row.get('content') or '').strip()
        if role not in {'user', 'assistant'} or not content:
            continue
        content = content[:min(1200, remaining)]
        if not content:
            break
        context.append({'role': role, 'content': content})
        remaining -= len(content)
    return list(reversed(context))


def _visual_arabic(value: str) -> str:
    """Return original Unicode text for native Windows/Tk font rendering.

    v3.0 pre-applied arabic_reshaper + python-bidi *before* Tk Text had
    wrapped a message, which scrambled words and broke Arabic letter joining.
    Pre-reordered Unicode also interferes with mixed Arabic/Latin content.
    Keep logical text in the widget; justify RTL by the existing message tag.
    Stored, shown and copied strings are now consistent.
    """
    return str(value or '')


def _btn(master, label, action, *, primary=False, quiet=False, width=None):
    bg = theme.ACCENT if primary else (theme.BG if quiet else theme.PANEL)
    fg = '#ffffff' if primary else theme.TEXT
    hover = theme.ACCENT_HOVER if primary else theme.SIDEBAR_HOVER
    button = tk.Button(master, text=_visual_arabic(label), command=action, font=('Segoe UI', 10, 'bold' if primary else 'normal'),
                       bg=bg, fg=fg, activebackground=hover, activeforeground=fg,
                       relief='flat', borderwidth=0, cursor='hand2', padx=15, pady=9,
                       highlightthickness=0, takefocus=True)
    if width is not None:
        button.configure(width=width)
    button.bind('<Enter>', lambda _event: button.configure(bg=hover))
    button.bind('<Leave>', lambda _event: button.configure(bg=bg))
    return button


def _safe_widget_label(widget, text):
    try:
        widget.configure(text=text)
    except (tk.TclError, AttributeError):
        pass


def apply_text_first_v300() -> None:
    global _INSTALLED
    if _INSTALLED:
        return
    from .ui.chat_window import ChatWindow
    from .ui.settings_view import SettingsView
    # Replace legacy Voice & local-Hammer settings with meaningful cloud-first
    # text-chat + microphone dictation settings (no TTS controls).
    old_settings_shell = SettingsView._build_shell

    def settings_shell(self):
        old_settings_shell(self)
        try:
            self.cat_buttons['voice'].configure(text=self.t('🎙 الإملاء إلى نص', '🎙 Voice typing'))
            self.cat_buttons['ai'].configure(text=self.t('GroqCloud والذكاء', 'GroqCloud AI'))
        except (KeyError, tk.TclError):
            pass

    def settings_voice_page(self):
        frame = self._section(
            self.t('الإملاء الصوتي إلى نص فقط', 'Speech-to-text only'),
            self.t('لا يوجد رد صوتي أو محادثة صوتية. الميكروفون يشتغل فقط بعد الضغط على زر الإملاء، والنص يبقى قابلًا للمراجعة قبل الإرسال.',
                   'No speech output. The mic only runs after you choose Dictate, and the text remains editable before sending.'),
        )
        self._row_check(frame, 1, self.t('السماح بالإملاء إلى النص', 'Enable dictation'),
                        'voice_enabled', self.settings.voice_enabled)
        try:
            from .voice.capture_v280 import input_devices
            devices = [d.label for d in input_devices()]
        except Exception:
            devices = []
        self._row_combo(frame, 2, self.t('الميكروفون', 'Microphone'), 'voice_input_device',
                        self.settings.voice_input_device, ['auto'] + devices, width=55)

    def settings_ai_page(self):
        frame = self._section('GroqCloud • GPT-OSS 120B', self.t(
            'الذكاء الاصطناعي يُشغّل على السحابة. عند تفعيل ذاكرة المحادثة تُرسل الرسائل الأخيرة لفهم المتابعة؛ تنفيذ العمليات يحتاج موافقة منفصلة.',
            'Cloud-hosted AI. With chat memory enabled, recent messages provide context. Actions require separate approval.'
        ))
        self._row_combo(frame, 1, self.t('حد طول الإجابة', 'Reply token limit'),
                        'max_response_tokens', self.settings.max_response_tokens, [128, 240, 384])
        self._row_combo(frame, 2, self.t('مهلة اتصال الطلب', 'Per-call timeout'),
                        'ai_timeout_seconds', self.settings.ai_timeout_seconds, [25, 45, 60, 90])

    SettingsView._build_shell = settings_shell
    SettingsView._page_voice = settings_voice_page
    SettingsView._page_ai = settings_ai_page

    def build(self):
        self._v260_serial = 0
        self._v260_cancel_event = None
        self._fast_voice_mode = ''
        self._fast_stream_active = False
        self._v270_preview_cancel = None
        self._v270_last_review = ''
        self._v300_mic_active = False
        self._v300_mic_generation = 0
        self._v300_mic_cancel = None
        self._v300_mic_service = None
        self._v300_mic_queue = queue.Queue()
        self._v300_request_at = None
        self._v300_last_status = ''
        self._v300_next_approval_check = 0.0
        self._v300_last_assistant_reply = ''
        self._voice_turn_started = False
        self.configure(padding=0)
        self.columnconfigure(0, weight=1)
        self.rowconfigure(1, weight=1)

        header = tk.Frame(self, bg=theme.PANEL, padx=25, pady=14)
        header.grid(row=0, column=0, sticky='ew')
        header.columnconfigure(0, weight=1)
        tk.Label(header, text=_visual_arabic(self.t('المساعد الشخصي', 'Your Assistant')), bg=theme.PANEL,
                 fg=theme.TEXT, font=('Segoe UI', 16, 'bold')).grid(row=0, column=0, sticky='w')
        tk.Label(header, text=_visual_arabic(self.t('محادثة خاصة • بدون تشغيل صوت', 'Private text chat • no speech output')),
                 bg=theme.PANEL, fg=theme.MUTED, font=('Segoe UI', 9)).grid(row=1, column=0, sticky='w', pady=(3, 0))
        self.model_state = tk.Label(header, text='● GroqCloud  •  GPT-OSS 120B', bg=theme.PANEL,
                                    fg=theme.SUCCESS, font=('Segoe UI', 9, 'bold'))
        self.model_state.grid(row=0, column=1, rowspan=2, sticky='e', padx=(10, 14))
        _btn(header, self.t('GitHub Desktop', 'GitHub Desktop'), self._v300_open_github, quiet=True).grid(row=0, column=2, rowspan=2, padx=4)
        _btn(header, self.t('حالة Git', 'Git status'), self._v300_git_status, quiet=True).grid(row=0, column=3, rowspan=2, padx=4)

        chat_container = tk.Frame(self, bg=theme.BG)
        chat_container.grid(row=1, column=0, sticky='nsew', padx=18, pady=(12, 0))
        chat_container.grid_columnconfigure(0, weight=1)
        chat_container.grid_rowconfigure(0, weight=1)
        self.chat = tk.Text(chat_container, state='disabled', wrap='word', bd=0, relief='flat',
                            highlightthickness=0, bg=theme.BG, fg=theme.TEXT,
                            selectbackground=theme.SIDEBAR_ACTIVE, font=('Segoe UI', 12),
                            padx=21, pady=15, spacing1=3, spacing2=4, spacing3=16)
        self.chat.grid(row=0, column=0, sticky='nsew')
        scroll = ttk.Scrollbar(chat_container, orient='vertical', command=self.chat.yview)
        scroll.grid(row=0, column=1, sticky='ns')
        self.chat.configure(yscrollcommand=scroll.set)
        self.chat.bind('<Button-3>', self._v300_chat_menu)
        self.chat.tag_configure('user_name', font=('Segoe UI', 10, 'bold'), foreground=theme.ACCENT, spacing1=16, justify='right')
        self.chat.tag_configure('assistant_name', font=('Segoe UI', 10, 'bold'), foreground=theme.SUCCESS, spacing1=16, justify='right')
        self.chat.tag_configure('msg_rtl', font=('Segoe UI', 12), foreground=theme.TEXT,
                                justify='right', lmargin1=25, lmargin2=25, rmargin=18, spacing3=17)
        self.chat.tag_configure('msg_ltr', font=('Segoe UI', 12), foreground=theme.TEXT,
                                justify='left', lmargin1=18, lmargin2=18, rmargin=25, spacing3=17)
        self.chat.tag_configure('system_hint', foreground=theme.MUTED, font=('Segoe UI', 10),
                                justify='center', spacing1=14, spacing3=12)
        self.chat.tag_configure('system_error', foreground=theme.DANGER, font=('Segoe UI', 10),
                                justify='center', spacing1=10, spacing3=12)

        # Approval is rendered inside the compact chat instead of old floating buttons.
        self._v270_review_frame = tk.Frame(self, bg=theme.PANEL, padx=20, pady=10)
        self._v270_review_frame.grid(row=2, column=0, sticky='ew', padx=20, pady=(0, 4))
        self._v270_review_frame.grid_remove()
        tk.Label(self._v270_review_frame, text=_visual_arabic(self.t('🔒 موافقتك مطلوبة قبل التنفيذ', '🔒 Review before execution')),
                 bg=theme.PANEL, fg=theme.TEXT, font=('Segoe UI', 10, 'bold')).pack(anchor='w')
        self._v270_review_text = tk.Label(self._v270_review_frame, text='', bg=theme.PANEL, fg=theme.TEXT,
                                          wraplength=750, justify='right', anchor='e', font=('Segoe UI', 10))
        self._v270_review_text.pack(fill='x', pady=8)
        approve_actions = tk.Frame(self._v270_review_frame, bg=theme.PANEL)
        approve_actions.pack(fill='x')
        self._v270_approve_button = _btn(approve_actions, self.t('موافق — نفّذ', 'Approve and run'), self._v270_approve, primary=True)
        self._v270_approve_button.pack(side='right', padx=4)
        _btn(approve_actions, self.t('إلغاء', 'Cancel'), self._v270_reject, quiet=True).pack(side='right', padx=4)

        detail_row = tk.Frame(self, bg=theme.BG)
        detail_row.grid(row=3, column=0, sticky='ew', padx=24)
        self.detail_btn = ttk.Button(detail_row, text=self.t('تفاصيل', 'Details'), command=self._toggle_details)
        self.detail_btn.pack(side='right')
        self.detail_btn.pack_forget()
        self.detail_box = tk.Text(detail_row, height=3, state='disabled', wrap='word',
                                  bg=theme.PANEL, fg=theme.MUTED, font=('Consolas', 9), relief='flat')

        footer = tk.Frame(self, bg=theme.PANEL, padx=20, pady=15)
        footer.grid(row=4, column=0, sticky='ew')
        footer.columnconfigure(0, weight=1)
        tk.Label(footer, text=_visual_arabic(self.t('اكتب رسالتك أو استخدم الإملاء', 'Write your message or use dictation')),
                 bg=theme.PANEL, fg=theme.MUTED, font=('Segoe UI', 10)).grid(row=0, column=0, sticky='w', pady=(0, 7))
        self.input = tk.Text(footer, height=3, wrap='word', undo=True,
                             bg=theme.INPUT, fg=theme.TEXT, insertbackground=theme.TEXT,
                             selectbackground=theme.SIDEBAR_ACTIVE, font=('Segoe UI', 12),
                             padx=13, pady=11, highlightthickness=1, highlightbackground=theme.BORDER,
                             highlightcolor=theme.ACCENT, bd=0, relief='flat', spacing2=3)
        self.input.grid(row=1, column=0, columnspan=5, sticky='ew')
        self.input.bind('<Return>', self._on_enter)
        self.input.bind('<Shift-Return>', self._on_shift_enter)
        self.input.focus_set()

        action_bar = tk.Frame(footer, bg=theme.PANEL)
        action_bar.grid(row=2, column=0, columnspan=5, sticky='ew', pady=(10, 0))
        action_bar.columnconfigure(2, weight=1)
        _btn(action_bar, self.t('إرفاق', 'Attach'), self._attach, quiet=True).grid(row=0, column=0, padx=(0, 6), sticky='w')
        self._v300_mic_button = _btn(action_bar, self.t('🎙 إملاء نص', '🎙 Dictate text'), self._v300_toggle_dictation, quiet=True)
        self._v300_mic_button.grid(row=0, column=1, padx=(0, 6), sticky='w')
        self.status = tk.Label(action_bar, text=_visual_arabic(self.t('جاهز', 'Ready')), bg=theme.PANEL,
                               fg=theme.MUTED, font=('Segoe UI', 9), anchor='e')
        self.status.grid(row=0, column=2, sticky='ew', padx=8)
        self._v300_stop_button = _btn(action_bar, self.t('إيقاف', 'Stop'), self._v300_stop, quiet=True)
        self._v300_stop_button.grid(row=0, column=3, padx=6)
        self.send_btn = _btn(action_bar, self.t('إرسال  ➤', 'Send  ➤'), self.send, primary=True)
        self.send_btn.grid(row=0, column=4, sticky='e', padx=(4, 0))
        self._v300_update_buttons()

    def append(self, role: str, message: str):
        text = str(message or '').strip()
        if not text:
            return
        self.chat.configure(state='normal')
        if role != 'user':
            self._v300_last_assistant_reply = text
        name = self.t('أنت', 'You') if role == 'user' else (self.settings.assistant_name or self.t('المساعدة', 'Assistant'))
        self.chat.insert('end', _visual_arabic(name) + '\n', 'user_name' if role == 'user' else 'assistant_name')
        tag = 'msg_rtl' if re.search(r'[\u0600-\u06ff]', text) else 'msg_ltr'
        self.chat.insert('end', _visual_arabic(text) + '\n\n', tag)
        self.chat.configure(state='disabled')
        self.chat.see('end')

    def chat_menu(self, event):
        menu = tk.Menu(self, tearoff=0)
        menu.add_command(label=_visual_arabic(self.t('نسخ آخر رد كامل', 'Copy latest reply')),
                         command=self._v300_copy_last_reply)
        try:
            menu.tk_popup(event.x_root, event.y_root)
        finally:
            menu.grab_release()

    def copy_last_reply(self):
        text = self._v300_last_assistant_reply
        if text:
            self.clipboard_clear()
            self.clipboard_append(text)  # Original unreshaped Arabic text.
            self.status.configure(text=_visual_arabic(self.t('تم نسخ آخر رد', 'Latest reply copied')))

    def hint(self, msg: str):
        self.chat.configure(state='normal')
        self.chat.insert('end', _visual_arabic(str(msg).strip()) + '\n\n', 'system_hint')
        self.chat.configure(state='disabled')
        self.chat.see('end')

    def load_history(self):
        history = self.db.recent_messages('hammer', 60, session_id=self.session_id)
        if not history:
            self._append_hint(self.t('أهلًا! اكتب طلبك أو اضغط «إملاء نص». ما رح أقرأ لك الرد بصوت.',
                                     'Welcome! Type or dictate. Replies stay in text.'))
        for entry in history:
            self._append(entry.get('role', 'assistant'), entry.get('content', ''))

    def update_buttons(self):
        try:
            self.send_btn.configure(state='disabled' if self.busy else 'normal')
            self._v270_approve_button.configure(state='disabled' if self.busy else 'normal')
            self._v300_mic_button.configure(text=_visual_arabic(self.t('■ إنهاء الإملاء', '■ Stop dictation') if self._v300_mic_active
                                              else self.t('🎙 إملاء نص', '🎙 Dictate text')))
        except tk.TclError:
            pass

    def open_github(self):
        ok, msg = open_github_desktop()
        self.status.configure(text=msg[:135])
        if not ok:
            self._append('assistant', msg)

    def git_status(self):
        self._append('assistant', local_github_status())

    def stop(self):
        if self._v300_mic_active:
            self._v300_stop_dictation()
        if getattr(self, '_v260_cancel_event', None) is not None:
            self._v260_cancel(quiet=False)
        self._v300_update_buttons()

    def send(self):
        text = self.input.get('1.0', 'end-1c').strip()
        if not text:
            return
        if self._v300_mic_active:
            self._v300_stop_dictation()
        if getattr(self, '_v260_cancel_event', None) is not None:
            self._v260_cancel(quiet=True)
        self._v260_serial += 1
        serial = self._v260_serial
        cancel_event = threading.Event()
        self._v260_cancel_event = cancel_event
        self._v300_request_at = time.monotonic()
        self.input.delete('1.0', 'end')
        self._append('user', text)
        self.db.add_message('user', text, 'hammer', self.session_id)
        self.db.rename_session_from_first_message(self.session_id, text)
        if self.on_session_title_changed:
            self.on_session_title_changed()
        self.db.add_activity('chat_request', f'session={self.session_id}; {text[:360]}')
        self.detail_btn.pack_forget()
        self.detail_box.pack_forget()

        # Context and an unapproved draft are not execution authorization.
        # Only the review button sets authorization, bound to the exact preview.
        is_click_approval = (text == 'نعم' and bool(getattr(self.controller, '_v270_authorization', None)))
        if not is_click_approval:
            self.controller._v270_authorization = None
            try:
                pending = self.db.get_pending_action(self.session_id)
                if pending and not pending_is_fresh(pending):
                    self.db.clear_pending_action(self.session_id)
            except Exception:
                pass
        history = chat_context(self.db, self.session_id, text)
        pending = self.db.get_pending_action(self.session_id)

        if is_single_facebook_link(text):
            answer = self.t('وصلني رابط فيسبوك. شو بدك أعمل عليه بالضبط؟ أقرأ الصفحة، أفحص منشور، أو أجهّز عملية للموافقة؟',
                            'I received the Facebook link. Should I inspect the page, check a post, or prepare an action for approval?')
            self._append('assistant', answer)
            self.db.add_message('assistant', answer, 'hammer', self.session_id)
            self._v260_cancel_event = None
            self.status.configure(text=self.t('جاهز', 'Ready'))
            self._v300_update_buttons()
            return

        self.busy = True
        self.status.configure(text=self.t('جاري الاتصال بـGroq…', 'Contacting Groq…'))
        self._v300_update_buttons()
        # Keep local execution permissions separate from conversational context.
        attachments = ', '.join(Path(p).name for p in self.attachments)
        prompt = text + (f'\n\nAttached task files: {attachments}' if attachments else '')
        self.attachments.clear()

        def queue_result(kind, value):
            if not cancel_event.is_set():
                self.result_q.put((kind, serial, value))

        def work():
            _CANCEL.event = cancel_event
            try:
                if (requires_local_tools(prompt) or is_click_approval or pending
                        or any(requires_local_tools(item['content']) for item in history[-4:])):
                    outcome = self.controller.handle(
                        QWEN, history, prompt, self.session_id,
                        max(96, min(400, int(self.settings.max_response_tokens))),
                        min(25, int(self.settings.ai_timeout_seconds)),
                        status=lambda message: queue_result('status', message),
                    )
                else:
                    # Ordinary conversation needs only one model response.
                    completion = self.engine.reply(
                        QWEN, history, prompt, max(96, min(400, int(self.settings.max_response_tokens))),
                        min(25, int(self.settings.ai_timeout_seconds)),
                        status=lambda message: queue_result('status', message),
                    )
                    outcome = AgentResponse(completion.text, used_model=True)
                _check_cancel()
                queue_result('reply', outcome)
            except TurnCancelled:
                pass
            except BaseException as exc:
                # BaseException is needed solely for the existing cancellation
                # sentinel; no exception is swallowed without feedback.
                queue_result('ai_error', f'{type(exc).__name__}: {exc}')
            finally:
                _CANCEL.event = None

        threading.Thread(target=work, daemon=True, name=f'yaa-v300-turn-{serial}').start()
        self.after(REQUEST_DEADLINE_MS, lambda: self._v300_timeout(serial))

    def timeout(self, serial):
        if serial != self._v260_serial or not self.busy:
            return
        self._v260_cancel(quiet=True)
        text = self.t('انتهت مهلة انتظار الطلب (50 ثانية). أوقفت انتظار الرد؛ جرّب أمرًا أقصر. إذا كانت هناك عملية خارجية قيد التنفيذ، افحص حالتها قبل تكرارها.',
                      'The request exceeded 50 seconds. Waiting was cancelled. If an external action was in progress, check its state before retrying.')
        self._append('assistant', text)
        self.status.configure(text=self.t('انتهت المهلة', 'Timed out'))
        self._v300_update_buttons()

    def poll(self):
        try:
            while True:
                kind, serial, value = self.result_q.get_nowait()
                if serial != self._v260_serial:
                    continue
                if kind == 'status':
                    msg = str(value)
                    if not msg.startswith(_STREAM_PREFIX):
                        self.status.configure(text=msg[:100])
                elif kind == 'reply':
                    result = value
                    self._append('assistant', result.text)
                    self.db.add_message('assistant', result.text, 'hammer', self.session_id)
                    self.last_detail = str(result.detail or '')
                    if self.last_detail:
                        self.detail_btn.pack(side='right')
                    self._v260_cancel_event = None
                    self.busy = False
                    self.status.configure(text=self.t('جاهز', 'Ready'))
                    self._v300_next_approval_check = 0
                    self._v300_update_buttons()
                    if self.on_activity:
                        self.on_activity()
                elif kind == 'ai_error':
                    self.last_detail = str(value)[:2500]
                    self._append('assistant', self.t('تعذر إكمال الطلب. راجع «تفاصيل» لمعرفة السبب.',
                                                    'Request failed. Open Details for the error.'))
                    self.detail_btn.pack(side='right')
                    self._v260_cancel_event = None
                    self.busy = False
                    self.status.configure(text=self.t('تعذر التنفيذ', 'Failed'))
                    self._v300_update_buttons()
        except queue.Empty:
            pass
        self._v300_poll_dictation()
        self._v300_refresh_approval()
        if self.winfo_exists():
            self.after(110 if self.busy or self._v300_mic_active else 1100, self._poll_results)

    def refresh_approval(self):
        now = time.monotonic()
        if now < getattr(self, '_v300_next_approval_check', 0):
            return
        self._v300_next_approval_check = now + (0.8 if self.busy else 3.0)
        try:
            pending = self.db.get_pending_action(self.session_id)
            sig = pending_signature(pending) if pending_is_fresh(pending) else ''
            if sig != self._v270_last_review:
                self._v270_last_review = sig
                if sig:
                    self._v270_review_text.configure(text=_visual_arabic(str(pending.get('summary') or '')[:2000]))
                    self._v270_review_frame.grid()
                else:
                    self._v270_review_frame.grid_remove()
            self._v270_approve_button.configure(state='disabled' if self.busy else 'normal')
        except (tk.TclError, AttributeError, ValueError):
            pass

    def start_or_stop_dictation(self):
        if self._v300_mic_active:
            self._v300_stop_dictation()
            return
        if not bool(getattr(self.settings, 'voice_enabled', True)):
            self.status.configure(text=self.t('فعّل الإملاء من الإعدادات.', 'Enable dictation in Settings.'))
            return
        if self.busy:
            self.status.configure(text=self.t('انتظر انتهاء الرد قبل الإملاء.', 'Wait for the reply before dictating.'))
            return
        from .voice.cloud_service import CloudVoiceService, VoiceCancelled
        self._v300_mic_generation += 1
        generation = self._v300_mic_generation
        self._v300_mic_active = True
        cancel = threading.Event()
        self._v300_mic_cancel = cancel
        self.status.configure(text=self.t('🎙 أسمعك… النص يظهر بعد كل جملة', '🎙 Listening… text appears after each phrase'))
        self._v300_update_buttons()
        service = CloudVoiceService(self.settings)
        self._v300_mic_service = service
        def work():
            # Repeated cloud STT turns with NO speech synthesis and NO auto-send.
            # Silence is harmless. At most one Whisper request at a time.
            while not cancel.is_set():
                try:
                    service.reset_cancel()
                    snippet = normalize_listen_text(service.listen_once(mode='dictation'))
                    if snippet and not cancel.is_set():
                        self._v300_mic_queue.put(('text', generation, snippet))
                except VoiceCancelled:
                    break
                except Exception as exc:
                    if cancel.is_set():
                        break
                    msg = str(exc)
                    # Local no-speech timeout can be retried during an open
                    # dictation session. Cloud failures are reported and stop.
                    if ('لا يصل صوت كاف' in msg or 'ما سمعت كلام' in msg):
                        continue
                    self._v300_mic_queue.put(('error', generation, msg))
                    break
            self._v300_mic_queue.put(('done', generation, ''))
        threading.Thread(target=work, name='yaa-v300-dictation', daemon=True).start()

    def stop_dictation(self):
        self._v300_mic_active = False
        self._v300_mic_generation += 1
        if self._v300_mic_cancel:
            self._v300_mic_cancel.set()
        svc = self._v300_mic_service
        if svc:
            svc.cancel()
        self._v300_mic_service = None
        self._v300_update_buttons()
        self.status.configure(text=self.t('الإملاء متوقف. راجع النص ثم اضغط إرسال.',
                                          'Dictation stopped. Review the text and press Send.'))

    def poll_dictation(self):
        try:
            while True:
                kind, generation, value = self._v300_mic_queue.get_nowait()
                if generation != self._v300_mic_generation:
                    continue
                if kind == 'text':
                    existing = self.input.get('1.0', 'end-1c')
                    prefix = ' ' if existing and not existing.endswith((' ', '\n')) else ''
                    self.input.insert('end', prefix + str(value))
                    self.input.see('end')
                    self.status.configure(text=self.t('✅ أضفت الكلام للنص؛ يمكنك المتابعة',
                                                       '✅ Text added; keep speaking or press Send'))
                elif kind == 'error':
                    self.status.configure(text=str(value)[:160])
                    self._v300_stop_dictation()
                elif kind == 'done' and self._v300_mic_active:
                    self._v300_mic_active = False
                    self._v300_update_buttons()
        except queue.Empty:
            pass

    def disable_voice_reply(self, *_args, **_kwargs):
        # The user explicitly requested ZERO TTS playback.
        self._voice_turn_started = False
        return None

    def approve(self):
        # Reuse deterministic v2.7 authorization signature and action gate.
        pending = self.db.get_pending_action(self.session_id)
        if self.busy or not pending or not pending_is_fresh(pending):
            self.status.configure(text=self.t('الموافقة لم تعد صالحة. أعد طلب الإجراء.', 'Approval expired; request again.'))
            return
        sig = pending_signature(pending)
        if sig != self._v270_last_review:
            self.status.configure(text=self.t('تفاصيل العملية تغيرت. راجعها قبل الموافقة.', 'Action changed; review it first.'))
            return
        from .review_voice_v270 import _CLICK_TTL_SECONDS
        self.controller._v270_authorization = (sig, time.monotonic() + _CLICK_TTL_SECONDS)
        self.prefill_and_send('نعم')

    def reject(self):
        if self.busy:
            return
        self.controller._v270_authorization = None
        self.db.clear_pending_action(self.session_id)
        self._v300_refresh_approval()
        self.status.configure(text=self.t('ألغيت العملية.', 'Action cancelled.'))

    def destroy(self):
        try:
            if self._v300_mic_active:
                self._v300_stop_dictation()
            if self._v260_cancel_event:
                self._v260_cancel(quiet=True)
        except (AttributeError, tk.TclError):
            pass
        return original_destroy(self)

    original_destroy = ChatWindow.destroy
    ChatWindow._build = build
    ChatWindow._append = append
    ChatWindow._append_hint = hint
    ChatWindow._load_history = load_history
    ChatWindow._poll_results = poll
    ChatWindow._maybe_speak_reply = disable_voice_reply
    ChatWindow._v300_update_buttons = update_buttons
    ChatWindow._v300_open_github = open_github
    ChatWindow._v300_git_status = git_status
    ChatWindow._v300_chat_menu = chat_menu
    ChatWindow._v300_copy_last_reply = copy_last_reply
    ChatWindow._v300_stop = stop
    ChatWindow._v300_timeout = timeout
    ChatWindow._v300_refresh_approval = refresh_approval
    ChatWindow._v300_toggle_dictation = start_or_stop_dictation
    ChatWindow._v300_stop_dictation = stop_dictation
    ChatWindow._v300_poll_dictation = poll_dictation
    ChatWindow._v270_approve = approve
    ChatWindow._v270_reject = reject
    ChatWindow.send = send
    ChatWindow.destroy = destroy
    ChatWindow._yaa_text_first_v300 = True
    _INSTALLED = True
