"""Your Assistant Agent v2.9: safe idle-first cloud client.

The cloud model, STT and TTS are invoked on user interaction, never by an idle
poll. This small compatibility layer keeps the existing UI and approved tasks,
but disables automatic legacy background work until the owner opts in.
"""
from __future__ import annotations

import os
import sys
from datetime import datetime
import threading

_INSTALLED = False


def chat_poll_delay_ms(*, busy: bool, live_voice: bool, queued: bool, visible: bool) -> int:
    """Keep interactive latency while avoiding 10 idle callbacks per second."""
    if busy or live_voice or queued:
        return 100
    return 1600 if visible else 5000


def status_poll_delay_ms(*, running_task: bool, visible: bool) -> int:
    return 4000 if running_task and visible else (20000 if visible else 60000)


def _install_ui_idle() -> None:
    from .ui.chat_window import ChatWindow
    from .ui.app import App
    from .startup import apply_startup_mode

    if getattr(App, "_yaa_v290_light", False):
        return

    original_after = ChatWindow.after

    def after(self, ms, func=None, *args):
        # All previous versions end their message polling with
        # self.after(100, self._poll_results). Intercept ONLY this callback;
        # unrelated UI timers and progress animations keep their own timing.
        if (func is not None and getattr(func, "__self__", None) is self
                and getattr(func, "__name__", "") == "_poll_results"
                and isinstance(ms, int) and ms <= 150):
            pending = False
            for name in ("result_q", "_fast_voice_events", "_v270_voice_events"):
                events = getattr(self, name, None)
                if events is not None:
                    try:
                        if not events.empty():
                            pending = True
                            break
                    except Exception:
                        pass
            try:
                visible = bool(self.winfo_viewable())
            except Exception:
                visible = True
            ms = chat_poll_delay_ms(
                busy=bool(getattr(self, "busy", False)),
                live_voice=bool(getattr(self, "_fast_voice_mode", "")),
                queued=pending,
                visible=visible,
            )
        return original_after(self, ms, func, *args)

    ChatWindow.after = after

    old_init = App.__init__
    def __init__(self, *args, **kwargs):
        old_init(self, *args, **kwargs)
        # v2.9 migration turns off *only this application's* Windows Run entry.
        # This is done before unlocking so an old tray autostart cannot persist
        # merely because the user dismissed the password prompt.
        try:
            apply_startup_mode(self.settings_obj.start_with_windows)
        except Exception:
            pass

    old_backup_poll = App._poll_backup_sync
    def backup_poll(self):
        self._backup_after_id = None
        if getattr(self.settings_obj, "auto_backup", False):
            return old_backup_poll(self)
        return None

    def schedule(self):
        # The base app (and old v2.8) previously created repeat backup timers.
        # Cancel every outstanding known timer before registering at most one.
        for name in ("_poll_after_id", "_idle_after_id", "_backup_after_id"):
            token = getattr(self, name, None)
            if token is not None:
                try:
                    self.after_cancel(token)
                except Exception:
                    pass
            setattr(self, name, None)
        self._poll_after_id = self.after(2000, self._poll_status)
        # GroqCloud has no local AI model to unload: no idle model timer.
        if getattr(self.settings_obj, "auto_backup", False):
            self._backup_after_id = self.after(60000, self._poll_backup_sync)

    def poll_status(self):
        if not self.winfo_exists():
            return
        try:
            if self.winfo_viewable():
                self._refresh_status_card()
        except Exception:
            pass
        try:
            running = bool(self.facebook and self.facebook.current_status().get("running"))
        except Exception:
            running = False
        try:
            visible = bool(self.winfo_viewable())
        except Exception:
            visible = True
        self._poll_after_id = self.after(
            status_poll_delay_ms(running_task=running, visible=visible),
            self._poll_status,
        )

    # The v2.8 poller is intentionally not scheduled, but retaining this method
    # avoids accidental rescheduling by callers of the legacy API.
    def idle_poll(self):
        self._idle_after_id = None
        return None

    old_shutdown = App._shutdown
    def shutdown(self):
        for name in ("_poll_after_id", "_idle_after_id", "_backup_after_id"):
            token = getattr(self, name, None)
            if token is not None:
                try:
                    self.after_cancel(token)
                except Exception:
                    pass
                setattr(self, name, None)
        return old_shutdown(self)

    App.__init__ = __init__
    App._schedule_background_polls = schedule
    App._poll_status = poll_status
    App._poll_idle_unload = idle_poll
    App._poll_backup_sync = backup_poll
    App._shutdown = shutdown
    App._yaa_v290_light = True


def _install_sched_idle() -> None:
    from .agent.facebook_service import FacebookService
    from .ui.tasks_view import TasksView
    from tkinter import messagebox, ttk
    import tkinter as tk

    if getattr(FacebookService, "_yaa_v290_scheduler", False):
        return
    old_start_scheduler = FacebookService.start_scheduler
    old_save_rule = FacebookService.save_rule

    def start_scheduler(self):
        # Avoid even creating a polling thread if no unattended work is approved.
        if not getattr(self.settings, "background_tasks_enabled", False):
            return
        if not getattr(self.settings, "smart_agent_enabled", True):
            return
        if not any(int(row.get("enabled", 0)) for row in self.db.list_rules(500)):
            return
        return old_start_scheduler(self)

    def save_rule(self, plan):
        result = old_save_rule(self, plan)
        if result.ok:
            self.start_scheduler()
        return result

    def scheduler_loop(self):
        # 30 seconds is adequate for minute-based scheduled rules, versus 2s
        # waking 1800 times per hour when nothing is happening.
        while not self._stop_event.wait(30.0):
            if not (self.settings.smart_agent_enabled
                    and getattr(self.settings, "background_tasks_enabled", False)):
                continue
            try:
                due = self.db.due_rules(datetime.now().replace(microsecond=0).isoformat())
                for rule in due:
                    if not rule or self._stop_event.is_set():
                        continue
                    # Schedule must be re-validated in case a rule was deleted
                    # or disabled after the due-list snapshot.
                    current = self.db.get_rule(int(rule["id"]))
                    if not current or not int(current.get("enabled", 0)):
                        continue
                    self.db.advance_rule(int(rule["id"]))
                    threading.Thread(
                        target=self._execute_rule_guarded,
                        args=(current,), daemon=True,
                        name=f"yaa-facebook-rule-{rule['id']}",
                    ).start()
            except Exception as exc:
                self.activity("scheduler_error", f"{type(exc).__name__}: {exc}")

    FacebookService.start_scheduler = start_scheduler
    FacebookService.save_rule = save_rule
    FacebookService._scheduler_loop = scheduler_loop
    FacebookService._yaa_v290_scheduler = True

    old_build = TasksView._build
    def build(self):
        old_build(self)
        actions = self.status.master
        enabled = bool(getattr(self.settings, "background_tasks_enabled", False))
        self._v290_bg_var = tk.BooleanVar(value=enabled)
        ttk.Checkbutton(
            actions,
            text=self.t("جدولة الخلفية (اختياري)", "Background tasks (opt-in)"),
            variable=self._v290_bg_var,
            command=self._v290_set_background_tasks,
        ).pack(side="right", padx=8)

    def set_background_tasks(self):
        enabled = bool(self._v290_bg_var.get())
        if enabled and not messagebox.askyesno(
            self.t("تشغيل جدولة الخلفية", "Enable background tasks"),
            self.t(
                "هذا يسمح بتنفيذ المهام المحفوظة تلقائيًا في أوقاتها حتى لو لم ترسل أمرًا. هل توافق؟",
                "Approved saved tasks can run unattended at their scheduled times. Enable?",
            ), parent=self,
        ):
            self._v290_bg_var.set(False)
            return
        self.settings.background_tasks_enabled = enabled
        self.settings.save()
        if enabled:
            # A prior OFF can still be stopping the old scheduler thread.
            # Give it time to exit before requesting a new scheduler instance.
            self.after(750, self.facebook.start_scheduler)
        else:
            # Stop future dispatch; any already running operation is controlled
            # by the existing Stop Task action.
            self.facebook._stop_event.set()
        self.status.config(text=self.t(
            "تم حفظ إعداد الجدولة؛ عند إيقافها لا تُحذف مهامك.",
            "Scheduling preference saved; tasks were not deleted.",
        ))

    TasksView._build = build
    TasksView._v290_set_background_tasks = set_background_tasks


def apply_lightweight_v290():
    global _INSTALLED
    if _INSTALLED:
        return
    _install_ui_idle()
    _install_sched_idle()
    _INSTALLED = True
