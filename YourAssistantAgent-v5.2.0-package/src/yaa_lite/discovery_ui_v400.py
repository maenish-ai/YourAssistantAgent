"""Opt-in Windows app inventory button for the existing text-first chat."""
import queue
import threading
from .windows_discovery_v400 import discover_apps, describe_apps

def apply_discovery_ui_v400():
    from .ui.chat_window import ChatWindow
    from .text_first_v300 import _btn
    if getattr(ChatWindow, '_yaa_discovery_v400', False):
        return
    original_build = ChatWindow._build
    original_destroy = ChatWindow.destroy

    def build(self):
        original_build(self)
        self._v400_alive = True
        self._v400_busy = False
        self._v400_results = queue.Queue()
        header = self.winfo_children()[0]
        self._v400_button = _btn(header, self.t('برامج Windows', 'Windows apps'), self._v400_discover)
        self._v400_button.grid(row=0, column=5, rowspan=2, padx=4)

    def discover(self):
        if self._v400_busy:
            return
        self._v400_busy = True
        self._v400_button.configure(state='disabled')
        self.status.configure(text=self.t('جاري فحص البرامج محليًا…', 'Discovering installed apps locally…'))
        def worker():
            try:
                result = describe_apps(discover_apps())
            except Exception as exc:
                result = f'تعذر اكتشاف البرامج: {type(exc).__name__}'
            self._v400_results.put(result)
        threading.Thread(target=worker, daemon=True, name='yaa-app-discovery').start()
        self.after(150, self._v400_poll)

    def poll(self):
        if not self._v400_alive:
            return
        try:
            result = self._v400_results.get_nowait()
        except queue.Empty:
            self.after(150, self._v400_poll)
            return
        self._v400_busy = False
        self._v400_button.configure(state='normal')
        self._append('assistant', result)
        self.status.configure(text=self.t('اكتمل فحص البرامج', 'App discovery complete'))

    def destroy(self):
        self._v400_alive = False
        return original_destroy(self)

    ChatWindow._build = build
    ChatWindow._v400_discover = discover
    ChatWindow._v400_poll = poll
    ChatWindow.destroy = destroy
    ChatWindow._yaa_discovery_v400 = True
