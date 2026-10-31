"""v2.8 — microphone diagnostics, safe task deletion, and economical background polls.

Installed once after v2.7 UI patches. Does not create a service, start a new
thread, open the microphone, or use the network merely by being imported.
"""
from __future__ import annotations

import queue
import tempfile
import threading
from pathlib import Path
from tkinter import ttk, messagebox
import tkinter as tk


def install_mic_ui() -> None:
    from .ui.chat_window import ChatWindow
    from .voice.capture_v280 import input_devices, capture_wav
    if getattr(ChatWindow, '_yaa_v280_mic', False):
        return
    old_build = ChatWindow._build

    def _build(self):
        old_build(self)
        composer = self.input.master
        ttk.Button(composer, text=self.t('🎛 فحص واختيار الميكروفون', '🎛 Microphone setup and test'),
                   command=self._v280_mic_setup).grid(row=3, column=0, columnspan=5,
                                                       sticky='w', padx=8, pady=(0, 8))

    def mic_setup(self):
        if getattr(self, '_v280_mic_window', None) and self._v280_mic_window.winfo_exists():
            self._v280_mic_window.lift()
            return
        window = tk.Toplevel(self)
        self._v280_mic_window = window
        window.title(self.t('إعداد الميكروفون — Your Assistant', 'Microphone setup — Your Assistant'))
        window.geometry('550x335')
        window.minsize(470, 315)
        window.transient(self.winfo_toplevel())
        window.columnconfigure(0, weight=1)
        window.protocol('WM_DELETE_WINDOW', window.destroy)
        ttk.Label(window, text=self.t('اختر مدخل الصوت اللي بتحكي فيه فعليًا:',
                                      'Choose the actual microphone you speak into:')).grid(
                                          row=0, column=0, sticky='w', padx=16, pady=(14, 5))
        status = tk.StringVar(value=self.t('اختبار الميكروفون محلي فقط؛ ما بنرسل التسجيل للسحابة.',
                                           'The microphone test is local; nothing is uploaded.'))
        try:
            devices = input_devices()  # No microphone stream is opened here.
            labels = [self.t('تلقائي — الافتراضي في ويندوز', 'Automatic — Windows default')] + [d.label for d in devices]
        except Exception as exc:
            devices = []
            labels = [self.t('تلقائي — الافتراضي في ويندوز', 'Automatic — Windows default')]
            status.set(str(exc))
        choice = tk.StringVar()
        saved = str(getattr(self.settings, 'voice_input_device', 'auto') or 'auto')
        choice.set(saved if saved in labels else (labels[0] if saved == 'auto' else saved))
        combo = ttk.Combobox(window, textvariable=choice, values=labels,
                             state='readonly', width=65)
        combo.grid(row=1, column=0, sticky='ew', padx=16)
        if choice.get() not in labels:
            combo.set(labels[0])
        progress = ttk.Progressbar(window, orient='horizontal', mode='determinate', maximum=100)
        progress.grid(row=2, column=0, sticky='ew', padx=16, pady=(18, 5))
        ttk.Label(window, textvariable=status, wraplength=495).grid(row=3, column=0,
                                                                      sticky='w', padx=16, pady=(5, 9))
        buttons = ttk.Frame(window)
        buttons.grid(row=4, column=0, sticky='w', padx=16, pady=5)
        events: queue.Queue = queue.Queue()
        job = {'running': False}

        def selected_key():
            val = choice.get()
            return 'auto' if val == labels[0] else val

        def save():
            if job['running']:
                status.set(self.t('انتظر انتهاء الاختبار أولاً.', 'Wait for the test to finish.'))
                return
            self.settings.voice_input_device = selected_key()
            self.settings.save()
            status.set(self.t('تم حفظ الميكروفون. استخدم «محادثة صوتية» للتجربة.',
                              'Microphone saved. Try Live conversation.'))

        def test():
            if job['running']:
                return
            job['running'] = True
            test_btn.state(['disabled'])
            progress['value'] = 0
            status.set(self.t('احكي الآن لمدة 4 ثوانٍ… بعدها رح تسمع تسجيلك.',
                              'Speak for 4 seconds; the recording will play back.'))
            requested_key = selected_key()
            def worker():
                try:
                    class InputSettings:
                        voice_input_device = requested_key
                    with tempfile.TemporaryDirectory(prefix='yaa_mic_test_') as td:
                        path = Path(td) / 'mic_test.wav'
                        report = capture_wav(path, InputSettings(), threading.Event(),
                                             level_callback=lambda x: events.put(('level', x)),
                                             diagnostic_seconds=4)
                        if report.peak_rms < 12:
                            raise RuntimeError(self.t('الميكروفون المختار لا يرسل أي إشارة صوت تقريبًا. جرّب مدخلًا آخر.',
                                                      'Almost no microphone signal; choose a different input.'))
                        events.put(('playing', report))
                        if __import__('os').name == 'nt':
                            import winsound
                            winsound.PlaySound(str(path), winsound.SND_FILENAME)
                        events.put(('done', report))
                except Exception as exc:
                    events.put(('error', str(exc)))
            threading.Thread(target=worker, name='yaa-mic-diagnostic', daemon=True).start()

        test_btn = ttk.Button(buttons, text=self.t('🎙 سجّل واسمع 4 ثوانٍ', '🎙 Record and listen (4s)'), command=test)
        test_btn.pack(side='left', padx=(0, 8))
        ttk.Button(buttons, text=self.t('حفظ الاختيار', 'Save selection'), command=save).pack(side='left')
        ttk.Label(window, wraplength=495,
                  text=self.t('إذا اشتغل التسجيل هون وما اشتغل مع Groq، وقتها بنفحص خطوة تحويل الصوت لنص فقط.',
                              'If playback works but Groq does not, check speech-to-text independently.')).grid(
                                  row=5, column=0, sticky='w', padx=16, pady=(12, 0))

        def poll():
            if not window.winfo_exists():
                return
            try:
                while True:
                    kind, data = events.get_nowait()
                    if kind == 'level':
                        progress['value'] = min(100, int(float(data) * 100))
                    elif kind == 'playing':
                        status.set(self.t(f"تم التقاط الصوت من {data.device_label} — جارٍ تشغيل التسجيل…",
                                          f"Audio captured via {data.device_label} — playing back…"))
                    elif kind == 'done':
                        job['running'] = False
                        test_btn.state(['!disabled'])
                        status.set(self.t(f'نجح التسجيل ({data.samplerate} Hz). إذا سمعت صوتك احفظ الاختيار.',
                                          f'Recorded ({data.samplerate} Hz). If playback sounded right, save.'))
                    elif kind == 'error':
                        job['running'] = False
                        test_btn.state(['!disabled'])
                        status.set(str(data))
            except queue.Empty:
                pass
            window.after(95, poll)
        window.after(95, poll)

    ChatWindow._build = _build
    ChatWindow._v280_mic_setup = mic_setup
    ChatWindow._yaa_v280_mic = True


def install_task_deletion() -> None:
    from .ui.tasks_view import TasksView
    if getattr(TasksView, '_yaa_v280_delete', False):
        return
    old_refresh = TasksView.refresh

    def delete_id(self, rule_id: int) -> None:
        rule = self.db.get_rule(int(rule_id))
        if not rule:
            self.status.config(text=self.t('المهمة غير موجودة أو تم حذفها.', 'Task no longer exists.'))
            self.refresh()
            return
        name = str(rule.get('name') or f"#{rule_id}")
        if not messagebox.askyesno(self.t('تأكيد حذف المهمة', 'Confirm task deletion'),
                                   self.t(f'حذف المهمة «{name}» نهائيًا؟', f'Delete task “{name}” permanently?'),
                                   parent=self):
            return
        # Never let a pending scheduler dispatch the deleted rule.
        self.db.set_rule_enabled(int(rule_id), False)
        active = self.facebook.current_status().get('active_rule_id') == int(rule_id)
        if active:
            self.facebook.stop_current()
            self.status.config(text=self.t('جاري إيقاف المهمة ثم حذفها…', 'Stopping the running task before deletion…'))
            attempts = {'count': 0}
            def wait_stop():
                if not self.winfo_exists():
                    return
                if self.facebook.current_status().get('active_rule_id') == int(rule_id):
                    attempts['count'] += 1
                    if attempts['count'] > 100:
                        self.status.config(text=self.t('المهمة ما زالت تتوقف. أعد المحاولة بعد توقفها.',
                                                       'Task is still stopping. Retry deletion once it stops.'))
                        return
                    self.after(300, wait_stop)
                else:
                    self.db.delete_rule(int(rule_id))
                    self.refresh()
                    self.status.config(text=self.t('تم حذف المهمة بعد توقفها.', 'Task deleted after stopping.'))
            self.after(300, wait_stop)
            return
        self.db.delete_rule(int(rule_id))
        self.refresh()
        self.status.config(text=self.t('تم حذف المهمة.', 'Task deleted.'))

    def refresh(self):
        old_refresh(self)
        if self.view_mode.get() == 'table' and self.tree:
            tree = self.tree
            tree.bind('<Delete>', lambda event: self.delete_selected() or 'break')
            tree.bind('<BackSpace>', lambda event: self.delete_selected() or 'break')
            menu = tk.Menu(tree, tearoff=False)
            menu.add_command(label=self.t('حذف المهمة', 'Delete task'), command=self.delete_selected)
            def right_click(event):
                item = tree.identify_row(event.y)
                if not item:
                    return
                tree.selection_set(item)
                tree.focus(item)
                try:
                    menu.tk_popup(event.x_root, event.y_root)
                finally:
                    menu.grab_release()
            tree.bind('<Button-3>', right_click)
            tree.bind('<Button-2>', right_click)
        else:
            # Original card mode already has Run/Pause buttons but no Delete.
            # Add a per-card button without touching the database/list renderer.
            def walk(widget):
                for child in widget.winfo_children():
                    if isinstance(child, ttk.LabelFrame):
                        title = str(child.cget('text'))
                        try:
                            rule_id = int(title.split()[0].lstrip('#'))
                        except (ValueError, IndexError):
                            continue
                        ttk.Button(child, text=self.t('🗑 حذف', '🗑 Delete'),
                                   command=lambda rid=rule_id: self._v280_delete_id(rid)).pack(
                                       side='left', padx=6, pady=(8, 0))
                    walk(child)
            walk(self.content)

    def delete_selected(self):
        rule_id = self._selected_id()
        if rule_id is None:
            self.status.config(text=self.t('اختر مهمة من الجدول أو احذفها من بطاقتها.',
                                          'Select a task or use Delete on its card.'))
            return
        self._v280_delete_id(rule_id)

    TasksView._v280_delete_id = delete_id
    TasksView.delete_selected = delete_selected
    TasksView.refresh = refresh
    TasksView._yaa_v280_delete = True


def install_lightweight_background() -> None:
    from .ui.app import App
    if getattr(App, '_yaa_v280_lightweight', False):
        return

    def poll_idle(self):
        """Only one timer. Never spawn another backup timer from idle polling."""
        if not self.winfo_exists():
            return
        # The brain is remote; no local model needs periodic unload.
        self._idle_after_id = self.after(300_000, self._poll_idle_unload)

    def poll_status(self):
        if not self.winfo_exists():
            return
        visible = self.state() not in ('withdrawn', 'iconic')
        if visible:
            self._refresh_status_card()
        self._poll_after_id = self.after(4000 if visible else 15000, self._poll_status)

    App._poll_idle_unload = poll_idle
    App._poll_status = poll_status
    App._yaa_v280_lightweight = True


def apply_repair_v280() -> None:
    install_mic_ui()
    install_task_deletion()
    install_lightweight_background()
