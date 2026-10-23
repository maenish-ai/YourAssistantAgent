"""Lightweight optional Tk UI integration; no background scan at startup."""
from __future__ import annotations

import os
import threading
import tkinter as tk
from pathlib import Path
from tkinter import messagebox


def apply_v410_ui():
    from .ui.app import App
    from .unified_v410 import inventory_windows, save_inventory
    if getattr(App, '_yaa_v410', False):
        return
    original_sidebar = App._build_sidebar
    original_close = App._on_close_request

    def sidebar(self):
        original_sidebar(self)
        try:
            # Explicit, on-demand discovery only; no registry access on startup.
            button = tk.Button(self.sidebar, text='🔎 اكتشاف برامج Windows',
                               command=lambda: discover(self))
            button.pack(side='bottom', fill='x', padx=8, pady=4)
            self._v410_discovery_button = button
        except tk.TclError:
            pass

    def discover(self):
        if getattr(self, '_v410_discovering', False):
            return
        if not messagebox.askyesno('Windows Discovery',
                                   'فحص قائمة البرامج المثبتة وحفظ أسمائها محلياً فقط؟', parent=self):
            return
        self._v410_discovering = True
        button = getattr(self, '_v410_discovery_button', None)
        if button:
            button.configure(state='disabled')

        def worker():
            try:
                programs = inventory_windows()
                base = Path(os.environ.get('LOCALAPPDATA') or Path.home()) / 'YourAssistantAgent'
                save_inventory(base / 'program_inventory.json', programs)
                result = ('ok', len(programs), str(base / 'program_inventory.json'))
            except Exception as exc:
                result = ('error', type(exc).__name__, str(exc))

            def finish():
                self._v410_discovering = False
                if button and button.winfo_exists():
                    button.configure(state='normal')
                if result[0] == 'ok':
                    messagebox.showinfo('Windows Discovery',
                                        f'تم فهرسة {result[1]} برنامج/اختصار محلياً.\n{result[2]}', parent=self)
                else:
                    messagebox.showerror('Windows Discovery',
                                         f'{result[1]}: {result[2]}', parent=self)
            try:
                self.after(0, finish)
            except tk.TclError:
                pass

        threading.Thread(target=worker, daemon=True, name='yaa-discovery').start()

    def close(self):
        # Force choice on X, without changing persistent user preferences.
        answer = messagebox.askyesnocancel(
            'Your Assistant Agent',
            'نعم: العمل بالخلفية (أيقونة النظام)\nلا: الخروج بالكامل\nإلغاء: العودة للبرنامج',
            parent=self)
        if answer is None:
            return
        if answer:
            if self._ensure_tray():
                self.withdraw()
            else:
                messagebox.showwarning('System tray', 'أيقونة النظام غير متاحة؛ ستبقى النافذة مفتوحة.', parent=self)
        else:
            self._shutdown()

    App._build_sidebar = sidebar
    App._on_close_request = close
    App._yaa_v410 = True
