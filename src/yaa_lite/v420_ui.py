"""Chat attachment UX; invoked explicitly by launcher after v3.0 UI patch."""
from __future__ import annotations

import tkinter as tk
from tkinter import filedialog, messagebox
from .attachments_v420 import inspect_files, summary, validate_files


def apply_v420_ui():
    from .ui.chat_window import ChatWindow
    if getattr(ChatWindow, '_yaa_v420', False):
        return
    old_build = ChatWindow._build
    old_send = ChatWindow.send

    def refresh(self):
        label = getattr(self, '_v420_files_label', None)
        if label and label.winfo_exists():
            names = [p.rsplit('/', 1)[-1].rsplit('\\', 1)[-1] for p in self.attachments]
            label.configure(text=('📎 ' + ', '.join(names[:4]) + (f' (+{len(names)-4})' if len(names) > 4 else '')) if names else 'No attachments')

    def attach(self):
        paths = filedialog.askopenfilenames(
            parent=self, title='Select files / اختر ملفات',
            filetypes=[('All supported files', '*.zip *.pdf *.docx *.xlsx *.pptx *.png *.jpg *.jpeg *.webp *.mp4 *.mov *.txt *.md *.py *.json *.csv'), ('All files', '*.*')])
        if not paths:
            return
        try:
            selected = list(dict.fromkeys([*self.attachments, *paths]))
            validate_files(selected)
            self.attachments[:] = selected
            refresh(self)
        except (OSError, ValueError) as exc:
            messagebox.showerror('Attachments', str(exc), parent=self)

    def clear(self):
        self.attachments.clear()
        refresh(self)

    def preview(self):
        if not self.attachments:
            messagebox.showinfo('Attachments', 'Choose files first / اختر الملفات أولاً', parent=self)
            return
        try:
            items = inspect_files(self.attachments)
            text = summary(items, include_content=False)
            messagebox.showinfo('Local attachment preview', text[:3000], parent=self)
        except (OSError, ValueError, zipfile.BadZipFile) as exc:
            messagebox.showerror('Attachments', str(exc), parent=self)

    def build(self):
        old_build(self)
        # Original Attach button exists in v3.0, but only passed filenames to AI.
        # Add a clearly visible attachment bar, with remove and local inspection.
        self._v420_files_label = tk.Label(self, text='No attachments', anchor='w',
                                           bg='#20232b', fg='white', padx=8)
        self._v420_files_label.grid(row=5, column=0, sticky='ew', padx=20)
        toolbar = tk.Frame(self, bg='#20232b')
        toolbar.grid(row=6, column=0, sticky='w', padx=20, pady=3)
        tk.Button(toolbar, text='＋ Add files / إضافة', command=lambda: attach(self)).pack(side='left', padx=3)
        tk.Button(toolbar, text='Preview / معاينة', command=lambda: preview(self)).pack(side='left', padx=3)
        tk.Button(toolbar, text='Clear / إزالة', command=lambda: clear(self)).pack(side='left', padx=3)
        refresh(self)

    def send(self):
        if not self.attachments:
            return old_send(self)
        if getattr(self, 'busy', False):
            return
        original = self.input.get('1.0', 'end-1c').strip()
        try:
            items = inspect_files(self.attachments)
        except Exception as exc:
            messagebox.showerror('Attachment inspection', str(exc), parent=self)
            return
        # Ask before sending any locally-derived metadata or text to cloud.
        choice = messagebox.askyesno(
            'Send attachment information?',
            'Send filenames, sizes and locally extracted short previews to the AI service?\n'
            'The actual files will NOT be uploaded. No Git changes will occur.\n\n'
            'إرسال أسماء الملفات ومعاينات نصية قصيرة إلى خدمة الذكاء؟ الملفات نفسها لن تُرفع.',
            parent=self)
        if not choice:
            return
        enriched = original + '\n\n' + summary(items, include_content=True)
        self.input.delete('1.0', 'end')
        self.input.insert('1.0', enriched)
        try:
            old_send(self)
        finally:
            refresh(self)

    # Import in preview's exception handler is intentionally stdlib only.
    import zipfile
    ChatWindow._build = build
    ChatWindow._attach = attach
    ChatWindow.send = send
    ChatWindow._yaa_v420 = True
