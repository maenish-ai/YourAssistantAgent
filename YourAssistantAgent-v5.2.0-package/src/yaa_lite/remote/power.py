"""Optional idle-sleep prevention while the companion is enabled and on AC."""
from __future__ import annotations
import os
import threading

CONTINUOUS = 0x80000000
SYSTEM_REQUIRED = 0x00000001


class WindowsPower:
    def __init__(self):
        import ctypes
        from ctypes import wintypes
        class Status(ctypes.Structure):
            _fields_ = [('ac', wintypes.BYTE), ('flag', wintypes.BYTE),
                        ('percent', wintypes.BYTE), ('status', wintypes.BYTE),
                        ('life', wintypes.DWORD), ('full_life', wintypes.DWORD)]
        self.ctypes, self.Status = ctypes, Status
        self.kernel = ctypes.WinDLL('kernel32', use_last_error=True)
        self.kernel.SetThreadExecutionState.argtypes = [wintypes.DWORD]
        self.kernel.SetThreadExecutionState.restype = wintypes.DWORD

    def on_ac(self):
        status = self.Status()
        return bool(self.kernel.GetSystemPowerStatus(self.ctypes.byref(status))) and status.ac == 1

    def set_state(self, flags):
        if not self.kernel.SetThreadExecutionState(flags):
            raise OSError('Windows rejected idle-sleep prevention')


class AwakeGuard:
    def __init__(self, enabled=False, *, backend=None, interval=20, activity=None):
        self.enabled = enabled is True
        self.backend, self.interval = backend, interval
        self.activity = activity or (lambda *_: None)
        self.stopped = threading.Event()
        self.thread = None

    def start(self):
        if not self.enabled or (self.backend is None and os.name != 'nt'): return
        if self.thread and self.thread.is_alive(): return
        self.stopped.clear()
        self.thread = threading.Thread(target=self._run, name='yaa-power-session', daemon=True)
        self.thread.start()

    def _run(self):
        backend = self.backend
        try:
            backend = backend or WindowsPower()
            while not self.stopped.is_set():
                backend.set_state(CONTINUOUS | (SYSTEM_REQUIRED if backend.on_ac() else 0))
                if self.stopped.wait(self.interval): break
        except Exception as exc:
            self.activity('remote_power_error', type(exc).__name__)
        finally:
            if backend:
                try: backend.set_state(CONTINUOUS)
                except Exception: pass

    def stop(self):
        self.stopped.set()
        if self.thread and self.thread is not threading.current_thread(): self.thread.join(timeout=1)
