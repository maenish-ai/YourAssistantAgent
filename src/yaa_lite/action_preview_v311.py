"""v3.1.1: explicit, read-only ZIP preview integrated with the Tk chat.

The user chooses both the ZIP and the destination folder. No extraction into
that destination, overwrite, commit, push or cloud transmission is performed.
"""
from __future__ import annotations

import threading
import queue
from pathlib import Path
from tkinter import filedialog

from .smart_actions_v310 import Workspace, ActionError


def preview_zip(archive: Path, destination: Path, staging: Path) -> dict:
    """Extract into an isolated staging directory and report changes only."""
    archive = Path(archive).expanduser().resolve()
    destination = Path(destination).expanduser().resolve()
    staging = Path(staging).expanduser().resolve()
    # Explicitly selected paths form the scope of this *single* read-only task.
    workspace = Workspace([archive.parent, destination, staging.parent], staging)
    result = workspace.stage_zip(archive)
    return workspace.compare(Path(result['staging']), destination)


def describe_diff(diff: dict, *, limit: int = 12) -> str:
    labels = [('added', 'جديد'), ('changed', 'مختلف'),
              ('unchanged', 'بدون تغيير'), ('blocked', 'محجوب (ملف حساس أو غير آمن)')]
    lines = ['نتيجة فحص ZIP — معاينة فقط، بدون تعديل المشروع:']
    for key, label in labels:
        values = diff.get(key, [])
        lines.append(f'• {label}: {len(values)}')
        lines.extend(f'   {name}' for name in values[:limit])
        if len(values) > limit:
            lines.append(f'   … و{len(values) - limit} ملفات إضافية')
    lines.append('لم يتم نسخ أي ملف إلى المشروع. الدمج يحتاج موافقة مستقلة.')
    return '\n'.join(lines)


def apply_action_preview_v311() -> None:
    """Add one opt-in button; do not alter the existing cloud/chat routing."""
    from .ui.chat_window import ChatWindow
    from .text_first_v300 import _btn
    import tkinter as tk

    if getattr(ChatWindow, '_yaa_action_preview_v311', False):
        return
    original_build = ChatWindow._build
    original_destroy = ChatWindow.destroy

    def build(self):
        original_build(self)
        self._v311_alive = True
        self._v311_preview_running = False
        header = self.winfo_children()[0]
        self._v311_preview_button = _btn(
            header, self.t('فحص ZIP', 'Inspect ZIP'), self._v311_choose_zip)
        # Independent small control: does not interfere with existing approval UI.
        self._v311_preview_button.grid(row=0, column=4, rowspan=2, padx=4)

    def choose_zip(self):
        if self._v311_preview_running:
            return
        zip_path = filedialog.askopenfilename(parent=self, title='اختار ملف ZIP للفحص',
                                               filetypes=[('ZIP archives', '*.zip')])
        if not zip_path:
            return
        folder = filedialog.askdirectory(parent=self, title='اختار مجلد المشروع للمقارنة')
        if not folder:
            return
        self._v311_preview_running = True
        self._v311_preview_button.configure(state='disabled')
        self.status.configure(text=self.t('جاري فحص ZIP بالخلفية…', 'Inspecting ZIP in background…'))
        self._append('user', f'فحص ZIP: {Path(zip_path).name} (معاينة فقط)')
        staging = Path.home() / 'Desktop' / 'AssistantWorkspace'
        def worker():
            try:
                outcome = describe_diff(preview_zip(Path(zip_path), Path(folder), staging))
            except Exception as exc:
                outcome = f'تعذر فحص ZIP: {type(exc).__name__}: {exc}'
            self._v311_results.put(outcome)
        threading.Thread(target=worker, name='yaa-zip-preview', daemon=True).start()
        self.after(150, self._v311_poll_preview)

    def poll_preview(self):
        if not getattr(self, '_v311_alive', False):
            return
        try:
            outcome = self._v311_results.get_nowait()
        except queue.Empty:
            if self._v311_preview_running:
                self.after(150, self._v311_poll_preview)
            return
        self._v311_preview_running = False
        self._v311_preview_button.configure(state='normal')
        self._append('assistant', outcome)
        self.status.configure(text=self.t('اكتملت المعاينة', 'Preview complete'))

    def destroy(self):
        self._v311_alive = False
        return original_destroy(self)

    ChatWindow._build = build
    ChatWindow._v311_choose_zip = choose_zip
    ChatWindow._v311_poll_preview = poll_preview
    ChatWindow.destroy = destroy
    ChatWindow._yaa_action_preview_v311 = True
