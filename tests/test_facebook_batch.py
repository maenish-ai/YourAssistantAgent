"""Concrete Facebook previews and batch execution without live publishing."""
import sqlite3
from types import SimpleNamespace

import pytest

from yaa_lite.agent.facebook_service import FacebookService
from yaa_lite.agent.legacy_smart import SmartPlan
from yaa_lite.config import Settings
from yaa_lite.personal_assistant_v220 import _campaign_preview, _tool_schemas, _install_group_filtering
from yaa_lite.storage.db import ChatDB


class Browser:
    def __init__(self):
        self.posts = [f'https://www.facebook.com/page/posts/{i}' for i in range(1, 9)]
        self.find_calls = 0
        self.shares = []
        self.outcome = 'published'
        self.login_error = None

    def ensure_logged_in(self):
        if self.login_error:
            raise RuntimeError(self.login_error)

    def find_recent_post_urls(self, source, limit=8):
        self.find_calls += 1
        return self.posts[:limit]

    def share_post_to_group(self, **arguments):
        self.shares.append(arguments)
        return self.outcome

    def stop(self):
        pass


@pytest.fixture
def setup(tmp_path, monkeypatch):
    monkeypatch.setattr(ChatDB, 'list_groups', ChatDB.list_groups)
    monkeypatch.setattr(ChatDB, '_yaa_v220_filter_patched', False, raising=False)
    _install_group_filtering()
    db = ChatDB(tmp_path / 'facebook.sqlite3')
    db.upsert_groups([
        {'name': 'North', 'url': 'https://www.facebook.com/groups/11'},
        {'name': 'South', 'url': 'https://www.facebook.com/groups/22'},
    ])
    settings = Settings(facebook_hourly_limit=100, facebook_daily_limit=200)
    browser = Browser()
    service = FacebookService(db, settings)
    monkeypatch.setattr(service, '_make_fb', lambda: browser)
    monkeypatch.setattr(service._task_cancel_event, 'wait', lambda timeout: False)
    return db, settings, service, browser


def snapshot_rule(db, service, *, post_count=4, **overrides):
    snapshot = service.preview_campaign('https://www.facebook.com/page', post_count=post_count)
    plan = SmartPlan('Batch', 'Share last four', 'https://www.facebook.com/page',
                     interval_seconds=30, **snapshot)
    for name, value in overrides.items():
        setattr(plan, name, value)
    rule_id = db.add_rule(plan)
    return db.get_rule(rule_id)


def test_four_posts_are_previewed_and_pinned_despite_source_and_group_drift(setup):
    db, settings, service, browser = setup
    rule = snapshot_rule(db, service)
    assert len(rule['post_urls']) == 4
    assert len(rule['selected_groups']) == 2
    assert rule['approval_snapshot'] == 1
    browser.posts.insert(0, 'https://www.facebook.com/page/posts/new')
    db.upsert_groups([
        {'name': 'Renamed North', 'url': 'https://www.facebook.com/groups/11'},
        {'name': 'New Group', 'url': 'https://www.facebook.com/groups/33'},
    ])
    callbacks = []
    service.add_completion_listener(lambda rule_id, result: callbacks.append((rule_id, result)))
    service._execute_rule_guarded(rule)
    result = service.rule_result(rule['id'])
    assert result['status'] == 'completed'
    assert result['published'] == 8
    assert result['total'] == 8
    assert browser.find_calls == 1  # Preview only; execution does not reselect.
    assert {item['post_url'] for item in browser.shares} == set(rule['post_urls'])
    assert {item['group_name'] for item in browser.shares} == {'North', 'South'}
    assert callbacks == [(rule['id'], result)]
    assert not service.current_status()['running']


def test_unknown_browser_outcome_never_claims_submission(setup):
    db, settings, service, browser = setup
    browser.outcome = 'clicked'
    rule = snapshot_rule(db, service, post_count=1)
    service._execute_rule_guarded(rule)
    result = service.rule_result(rule['id'])
    assert result['status'] == 'failed'
    assert result['published'] == result['submitted'] == result['pending_approval'] == 0
    assert result['failed'] == 2


def test_pending_approval_and_no_repeat_are_reported_separately(setup):
    db, settings, service, browser = setup
    browser.outcome = 'pending_approval'
    rule = snapshot_rule(db, service, post_count=1)
    service._execute_rule_guarded(rule)
    assert service.rule_result(rule['id'])['pending_approval'] == 2
    assert service.rule_result(rule['id'])['published'] == 0
    service._execute_rule_guarded(rule)
    assert service.rule_result(rule['id'])['skipped'] == 2
    assert len(browser.shares) == 2


def test_batch_caps_apply_across_post_group_pairs(setup):
    db, settings, service, browser = setup
    settings.facebook_hourly_limit = 3
    rule = snapshot_rule(db, service)
    service._execute_rule_guarded(rule)
    result = service.rule_result(rule['id'])
    assert result['status'] == 'limited'
    assert result['published'] == 3
    assert len(browser.shares) == 3


def test_preview_requires_exact_count_and_valid_facebook_urls(setup):
    db, settings, service, browser = setup
    browser.posts = browser.posts[:2]
    with pytest.raises(ValueError, match='Requested 4'):
        service.preview_campaign('https://www.facebook.com/page', post_count=4)
    for bad in ('https://facebook.com.evil.example/page', 'http://facebook.com/page',
                'https://name:password@facebook.com/page'):
        with pytest.raises(ValueError):
            service.preview_campaign(bad)
    assert browser.shares == []


def test_missing_publishing_login_creates_no_approvable_draft(setup):
    db, settings, service, browser = setup
    browser.login_error = 'Publishing browser requires manual sign-in'
    session = db.create_session('hammer')
    controller = SimpleNamespace(db=db, settings=settings, facebook=service,
                                 t=lambda ar, en: en, _activity=lambda *args: None)
    reply = _campaign_preview(controller, 'Share last four',
                              {'source_page_url': 'https://www.facebook.com/page', 'post_count': 4}, session)
    assert 'Nothing was published' in reply.text
    assert 'managed publishing browser' in reply.text
    assert db.get_pending_action(session) is None
    assert browser.shares == []


def test_new_draft_contains_full_actual_targets_and_defaults_to_one_off(setup):
    db, settings, service, browser = setup
    session = db.create_session('hammer')
    controller = SimpleNamespace(db=db, settings=settings, facebook=service,
                                 t=lambda ar, en: en, _activity=lambda *args: None)
    reply = _campaign_preview(controller, 'Share last four',
                              {'source_page_url': 'https://www.facebook.com/page', 'post_count': 4}, session)
    pending = db.get_pending_action(session)
    assert pending['arguments']['run_immediately']
    plan = pending['arguments']['plan']
    assert plan['post_count'] == 4
    assert len(plan['post_urls']) == 4
    assert all(url in reply.text for url in plan['post_urls'])
    assert all(g['name'] in reply.text and g['url'] in reply.text for g in plan['selected_groups'])
    assert db.list_rules() == []
    assert browser.shares == []


def test_busy_service_does_not_claim_a_task_started(setup):
    db, settings, service, browser = setup
    rule = snapshot_rule(db, service, post_count=1)
    service._exec_lock.acquire()
    try:
        assert not service.run_rule_now(rule['id']).ok
    finally:
        service._exec_lock.release()
    assert browser.shares == []


def test_snapshot_columns_migrate_existing_rule_database(tmp_path):
    path = tmp_path / 'legacy.sqlite3'
    with sqlite3.connect(path) as con:
        con.execute('''CREATE TABLE smart_rules (
            id INTEGER PRIMARY KEY, name TEXT, command_text TEXT, source_page_url TEXT,
            weekdays TEXT, run_time TEXT, run_once_at TEXT, post_mode TEXT, post_offset INTEGER,
            group_keyword TEXT, max_groups INTEGER, interval_seconds INTEGER, no_repeat_days INTEGER,
            share_mode TEXT, next_run_at TEXT, enabled INTEGER, created_at TEXT)''')
        con.execute("INSERT INTO smart_rules(id,name,weekdays) VALUES(1,'legacy','[]')")
    db = ChatDB(path)
    rule = db.get_rule(1)
    assert rule['name'] == 'legacy'
    assert rule['post_count'] == 1
    assert rule['post_urls'] == rule['selected_groups'] == []
    assert not rule['approval_snapshot']


def test_model_schema_exposes_bounded_post_count():
    tool = next(t for t in _tool_schemas() if t['function']['name'] == 'draft_facebook_campaign')
    count = tool['function']['parameters']['properties']['post_count']
    assert count['minimum'] == 1 and count['maximum'] == 4


def test_dedicated_publishing_login_is_available_and_not_routed_to_normal_browser(setup):
    from yaa_lite.fast_live_v250 import fast_facebook_intent
    from yaa_lite.review_voice_v270 import permitted_mutation
    db, settings, service, browser = setup
    browser.open_manual_login = lambda: 'dedicated-test-profile'
    assert permitted_mutation('open_facebook_publishing_login')
    names = {tool['function']['name'] for tool in _tool_schemas()}
    assert 'open_facebook_publishing_login' in names
    assert fast_facebook_intent('check Facebook managed publishing session') is None
    assert fast_facebook_intent('افحص فيسبوك في متصفح النشر') is None
    result = service.open_publishing_login()
    assert result.ok and 'متصفح النشر' in result.message
    assert browser.shares == []


@pytest.mark.parametrize('background_enabled', [False, True])
def test_approved_schedule_starts_only_when_background_tasks_are_enabled(tmp_path, background_enabled):
    import os
    from pathlib import Path
    import subprocess
    import sys
    script = r'''
import sys
from pathlib import Path
from types import SimpleNamespace
from yaa_lite.bootstrap import configure_application
configure_application()
from yaa_lite.agent.tools import ToolRegistry
from yaa_lite.config import Settings
from yaa_lite.review_voice_v270 import execute_reviewed_action, pending_signature
from yaa_lite.storage.db import ChatDB

enabled = sys.argv[2] == 'True'
settings = Settings(background_tasks_enabled=enabled)
starts = []
facebook = SimpleNamespace(settings=settings, activity=lambda *args: None,
                           start_scheduler=lambda: starts.append(True))
db = ChatDB(Path(sys.argv[1]))
session = db.create_session('hammer')
plan = {'source_page_url': 'https://www.facebook.com/page', 'run_time': '20:00',
        'post_urls': ['https://www.facebook.com/page/posts/1'],
        'selected_groups': [{'id': 1, 'name': 'Reviewed group', 'url': 'https://www.facebook.com/groups/1'}],
        'approval_snapshot': True, 'no_repeat_days': 0}
db.set_pending_action(session, 'approve_facebook_campaign',
                      {'plan': plan, 'run_immediately': False}, 'Reviewed scheduled targets')
controller = SimpleNamespace(db=db, tools=ToolRegistry(db, facebook))
result = execute_reviewed_action(controller, session, pending_signature(db.get_pending_action(session)))
assert result.ok, result.text
assert result.data['scheduled_active'] is enabled
assert starts == ([True] if enabled else [])
assert settings.background_tasks_enabled is enabled
assert db.get_rule(result.data['rule_id'])['no_repeat_days'] == 0
assert ('scheduling is disabled' in result.text) is (not enabled)
'''
    root = Path(__file__).resolve().parents[1]
    result = subprocess.run([sys.executable, '-c', script, str(tmp_path / 'schedule.sqlite3'), str(background_enabled)],
                            cwd=root, env={**os.environ, 'PYTHONPATH': str(root / 'src')},
                            capture_output=True, text=True, timeout=20)
    assert result.returncode == 0, result.stdout + result.stderr
