"""v2.9 idle-first regression tests; never start Windows, browser or cloud."""
from __future__ import annotations

import json
from pathlib import Path
from types import SimpleNamespace

import pytest

from yaa_lite.config import Settings
from yaa_lite.lightweight_v290 import chat_poll_delay_ms, status_poll_delay_ms


def test_chat_idle_does_not_poll_ten_times_per_second():
    assert chat_poll_delay_ms(busy=False, live_voice=False, queued=False, visible=True) >= 1500


def test_hidden_window_polls_even_less_often():
    assert chat_poll_delay_ms(busy=False, live_voice=False, queued=False, visible=False) >= 4000


@pytest.mark.parametrize("flags", [
    dict(busy=True,live_voice=False,queued=False),
    dict(busy=False,live_voice=True,queued=False),
    dict(busy=False,live_voice=False,queued=True),
])
def test_busy_voice_or_pending_message_remains_responsive(flags):
    assert chat_poll_delay_ms(**flags, visible=True) <= 120


def test_sidebar_is_slow_at_rest_but_updates_active_task():
    assert status_poll_delay_ms(running_task=False, visible=True) >= 15000
    assert status_poll_delay_ms(running_task=False, visible=False) >= 60000
    assert status_poll_delay_ms(running_task=True, visible=True) <= 5000


def test_fresh_install_defaults_are_safe():
    s = Settings()
    assert s.close_behavior == 'exit'
    assert s.start_with_windows == 'off'
    assert s.facebook_auto_check is False
    assert s.auto_backup is False
    assert s.background_tasks_enabled is False


def test_v28_settings_migration_disables_autostart_not_accounts(monkeypatch, tmp_path):
    import yaa_lite.config as config
    monkeypatch.setattr(config, 'config_dir', lambda: tmp_path)
    (tmp_path/'settings.json').write_text(json.dumps({
        'close_behavior':'tray', 'start_with_windows':'tray',
        'facebook_auto_check':True, 'auto_backup':True,
        'default_source_page':'https://www.facebook.com/example',
        'voice_enabled':True,
        'first_run_complete':True,
    }),encoding='utf8')
    s=Settings.load()
    assert s.close_behavior=='exit'
    assert s.start_with_windows=='off'
    assert s.auto_backup is False
    assert s.facebook_auto_check is False
    assert s.background_tasks_enabled is False
    assert s.default_source_page=='https://www.facebook.com/example'
    assert s.first_run_complete
    s.save()
    assert Settings.load().lightweight_defaults_v290


def test_explicit_v29_preferences_are_kept(monkeypatch,tmp_path):
    import yaa_lite.config as config
    monkeypatch.setattr(config, 'config_dir', lambda: tmp_path)
    (tmp_path/'settings.json').write_text(json.dumps({
        'lightweight_defaults_v290':True,
        'background_tasks_enabled':True, 'auto_backup':True,
        'close_behavior':'tray','start_with_windows':'tray',
    }),encoding='utf8')
    s=Settings.load()
    assert s.background_tasks_enabled and s.auto_backup
    assert s.close_behavior=='tray' and s.start_with_windows=='tray'


def test_installer_does_not_launch_new_exe_unattended():
    root=Path(__file__).resolve().parents[1]
    script=(root/'installer'/'YourAssistantAgent.iss').read_text(encoding='utf8')
    run_section=script.split('[Run]',1)[1].split('[',1)[0]
    assert 'unchecked' in run_section


def test_launcher_applies_lightweight_after_old_patches():
    root=Path(__file__).resolve().parents[1]
    launcher=(root/'launcher.py').read_text(encoding='utf8')
    bootstrap=(root/'src/yaa_lite/bootstrap.py').read_text(encoding='utf8')
    assert bootstrap.index('apply_repair_v280()') < bootstrap.index('apply_lightweight_v290()')
    assert 'from yaa_lite.main import main' in launcher


def test_idle_callback_throttling_integration(monkeypatch):
    import sys, types
    import yaa_lite.lightweight_v290 as mod

    starts = []
    chat_mod = types.ModuleType('yaa_lite.ui.chat_window')
    app_mod = types.ModuleType('yaa_lite.ui.app')
    startup_mod = types.ModuleType('yaa_lite.startup')
    startup_mod.apply_startup_mode = starts.append

    class FakeChat:
        def __init__(self):
            import queue
            self.busy = False
            self._fast_voice_mode = ''
            self.result_q = queue.Queue()
            self.calls=[]
        def winfo_viewable(self):return True
        def after(self, ms, func=None, *args):
            self.calls.append(ms)
            return 'timer'
        def _poll_results(self):pass

    class FakeApp:
        def __init__(self):
            self.settings_obj=Settings()
            self.calls=[]
            self._poll_after_id=self._idle_after_id=self._backup_after_id=None
            self.facebook=None
        def after(self,ms,func):
            self.calls.append((ms,func.__name__))
            return str(len(self.calls))
        def after_cancel(self,id):pass
        def winfo_exists(self):return True
        def winfo_viewable(self):return True
        def _refresh_status_card(self):pass
        def _schedule_background_polls(self):pass
        def _poll_status(self):pass
        def _poll_idle_unload(self):pass
        def _poll_backup_sync(self):pass
        def _shutdown(self):pass

    chat_mod.ChatWindow=FakeChat
    app_mod.App=FakeApp
    monkeypatch.setitem(sys.modules,'yaa_lite.ui.chat_window',chat_mod)
    monkeypatch.setitem(sys.modules,'yaa_lite.ui.app',app_mod)
    monkeypatch.setitem(sys.modules,'yaa_lite.startup',startup_mod)
    mod._install_ui_idle()
    chat=FakeChat()
    chat.after(100,chat._poll_results)
    assert chat.calls[-1] == 1600
    chat.busy=True
    chat.after(100,chat._poll_results)
    assert chat.calls[-1]==100
    app=FakeApp()
    assert starts==['off']
    app._schedule_background_polls()
    assert len(app.calls)==1
    assert app.calls[0][1]=='poll_status'
    app._poll_status()
    assert app.calls[-1][0]==20000
    # With explicit opt-in to backups exactly one poll gets scheduled.
    app.settings_obj.auto_backup=True
    app._schedule_background_polls()
    assert [x[1] for x in app.calls[-2:]]==['poll_status','backup_poll']


def test_scheduler_never_starts_without_opt_in(monkeypatch):
    import sys, types
    import yaa_lite.lightweight_v290 as mod
    fb_mod=types.ModuleType('yaa_lite.agent.facebook_service')
    task_mod=types.ModuleType('yaa_lite.ui.tasks_view')

    class FakeFacebook:
        def __init__(self):
            self.settings=Settings()
            self.db=SimpleNamespace(list_rules=lambda max_items: [{'id':1,'enabled':1}])
            self.start_count=0
        def start_scheduler(self):self.start_count += 1
        def save_rule(self, plan):return SimpleNamespace(ok=True)
        def _scheduler_loop(self):pass

    class FakeTasks:
        def _build(self):pass
    fb_mod.FacebookService=FakeFacebook
    task_mod.TasksView=FakeTasks
    monkeypatch.setitem(sys.modules,'yaa_lite.agent.facebook_service',fb_mod)
    monkeypatch.setitem(sys.modules,'yaa_lite.ui.tasks_view',task_mod)
    mod._install_sched_idle()
    fb=FakeFacebook()
    fb.start_scheduler()
    assert fb.start_count == 0
    fb.settings.background_tasks_enabled=True
    fb.start_scheduler()
    assert fb.start_count == 1
    fb.db.list_rules=lambda max_items: []
    fb.start_scheduler()
    assert fb.start_count == 1
