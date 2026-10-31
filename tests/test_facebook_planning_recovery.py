"""Regression coverage for Facebook planning, without accounts or publishing."""
import json
from pathlib import Path
import subprocess
import sys
from types import SimpleNamespace

import pytest

from yaa_lite.agent.orchestrator import SmartAgentController
from yaa_lite.agent.tools import ToolRegistry
from yaa_lite.config import Settings
from yaa_lite.personal_assistant_v220 import (
    _install_personal_controller,
    _install_tool_registry_extensions,
)
from yaa_lite.storage.db import ChatDB


@pytest.fixture
def planning_stack(monkeypatch, tmp_path):
    # Isolate these class patches from the rest of the versioned bootstrap.
    for cls, names in (
        (ToolRegistry, ("__init__", "execute")),
        (SmartAgentController, ("handle",)),
    ):
        for name in names:
            monkeypatch.setattr(cls, name, getattr(cls, name))
        monkeypatch.setattr(cls, "_yaa_v220_patched", False, raising=False)
    _install_tool_registry_extensions()
    _install_personal_controller()
    return ChatDB(tmp_path / "planning.sqlite3")


@pytest.mark.parametrize("limit", ["all", [10], {"count": 10}])
def test_invalid_group_limit_is_recoverable_tool_result(planning_stack, limit):
    tools = ToolRegistry(planning_stack, SimpleNamespace())
    result = tools.execute("search_facebook_groups", {"limit": limit})
    assert not result.ok
    assert "integer" in result.text
    assert planning_stack.list_rules() == []


def test_invalid_rule_id_keeps_valid_tool_transcript(planning_stack):
    calls = []

    def native_turn(profile, messages, **kwargs):
        calls.append(True)
        if len(calls) == 1:
            return {"content": "", "tool_calls": [{
                "id": "call-invalid", "name": "run_facebook_rule_now",
                "arguments": {"rule_id": "missing"},
            }]}
        # A provider rejects a flattened {name, arguments} call on this turn.
        call = messages[-2]["tool_calls"][0]
        assert call["id"] == "call-invalid" and call["type"] == "function"
        assert call["function"]["name"] == "run_facebook_rule_now"
        assert json.loads(call["function"]["arguments"]) == {"rule_id": "missing"}
        assert messages[-1]["tool_call_id"] == "call-invalid"
        assert messages[-1]["content"] == "Invalid task ID."
        return {"content": "حدد رقم المهمة المطلوب تشغيلها.", "tool_calls": []}

    db = planning_stack
    session = db.create_session("hammer")
    engine = SimpleNamespace(runtime=SimpleNamespace(native_turn=native_turn))
    controller = SmartAgentController(db, Settings(), engine, SimpleNamespace())
    reply = controller.handle(None, [], "شغل المهمة", session, 256, 10)
    assert reply.text == "حدد رقم المهمة المطلوب تشغيلها."
    assert len(calls) == 2
    assert db.get_pending_action(session) is None
    assert db.list_rules() == []


def test_planning_can_finish_multi_step_reads_without_stopping_after_five(planning_stack):
    calls = []
    def native_turn(profile, messages, **kwargs):
        calls.append(True)
        if len(calls) <= 6:
            return {'content': '', 'tool_calls': [{'id': f'check-{len(calls)}',
                    'name': 'app_status', 'arguments': {}}]}
        return {'content': 'اكتملت القراءة', 'tool_calls': []}
    db = planning_stack
    controller = SmartAgentController(db, Settings(),
        SimpleNamespace(runtime=SimpleNamespace(native_turn=native_turn)),
        SimpleNamespace(status_text=lambda: 'connected'))
    reply = controller.handle(None, [], 'اقرأ حالة المهمة والخطوات', db.create_session('hammer'), 512, 10)
    assert len(calls) == 7 and reply.text == 'اكتملت القراءة'
    assert db.list_rules() == []


ARABIC_FACEBOOK_FLOW = r'''
import json
from pathlib import Path
import sys
from types import SimpleNamespace

from yaa_lite.bootstrap import configure_application
configure_application()
from yaa_lite.agent.facebook_service import FacebookActionResult
from yaa_lite.agent.orchestrator import SmartAgentController
from yaa_lite.config import Settings
from yaa_lite.personal_assistant_v220 import decode_group_filter
from yaa_lite.storage.db import ChatDB

db = ChatDB(Path(sys.argv[1]))
session = db.create_session('hammer')
source = 'https://www.facebook.com/owner.page'
post = source + '/posts/123'
events = []

def search_pages(query):
    assert query == 'صفحتي للساتلايت'
    events.append('pages')
    return FacebookActionResult(True, json.dumps({'pages': [
        {'name': query, 'url': source},
    ]}, ensure_ascii=False), 1)

def discover_groups(limit=500, deep=True):
    events.append('discover')
    db.upsert_groups([
        {'name': 'سورية للساتلايت', 'url': 'https://www.facebook.com/groups/11'},
        {'name': 'مجموعات عامة', 'url': 'https://www.facebook.com/groups/22'},
    ])
    return FacebookActionResult(True, 'تم اكتشاف المجموعات', 2)

def preview_campaign(source_page_url, group_keyword, max_groups, post_offset, post_count):
    events.append('preview')
    assert source_page_url == source
    assert decode_group_filter(group_keyword)['include_keywords'] == ['سورية']
    assert post_offset == 0 and post_count == 1
    groups = db.list_groups(keyword=group_keyword, limit=max_groups)
    assert [g['name'] for g in groups] == ['سورية للساتلايت']
    return {'post_urls': [post], 'selected_groups': groups,
            'post_count': 1, 'approval_snapshot': True}

def recent_posts(source_page_url, count=1):
    assert source_page_url == source and count == 1
    events.append('read')
    return FacebookActionResult(True, json.dumps({'visible_recent_post_urls': [post]}), 1)

class Runtime:
    index = 0
    def native_turn(self, profile, messages, **kwargs):
        index = self.index
        self.index += 1
        if index == 0:
            name, args = 'search_facebook_pages', {'query': 'صفحتي للساتلايت'}
        elif index == 1:
            assert source in messages[-1]['content']
            name, args = 'discover_facebook_groups', {}
        elif index == 2:
            name, args = 'search_facebook_groups', {'include_keywords': ['سورية'], 'limit': 'all'}
        elif index == 3:
            assert messages[-1]['content'].startswith('ERROR: Invalid group limit')
            name, args = 'search_facebook_groups', {'include_keywords': ['سورية']}
        else:
            assert index == 4
            result = json.loads(messages[-1]['content'])
            assert result['count'] == 1
            assert result['filter']['include_keywords'] == ['سورية']
            # The app must carry forward this turn's observed group selection.
            name, args = 'draft_facebook_campaign', {'source_page_url': source, 'run_immediately': True}
        return {'content': '', 'tool_calls': [
            {'id': 'call' + str(index), 'name': name, 'arguments': args},
        ]}

runtime = Runtime()
facebook = SimpleNamespace(search_pages=search_pages, discover_groups=discover_groups,
                           preview_campaign=preview_campaign, recent_posts=recent_posts)
controller = SmartAgentController(db, Settings(), SimpleNamespace(runtime=runtime), facebook)
reply = controller.handle(None, [],
    'ابحث عن صفحتي للساتلايت وجهز آخر منشور للنشر على المجموعات التي تحتوي على كلمة سورية',
    session, 512, 10)
assert runtime.index == 5
assert events == ['pages', 'discover', 'preview']
assert post in reply.text and 'سورية للساتلايت' in reply.text
assert 'مجموعات عامة' not in reply.text
pending = db.get_pending_action(session)
assert pending['tool_name'] == 'approve_facebook_campaign'
assert pending['arguments']['plan']['selected_groups'][0]['name'] == 'سورية للساتلايت'
assert len(pending['arguments']['plan']['selected_groups']) == 1
assert db.list_rules() == []  # Only a reviewable preview; never publish here.
read = controller.tools.execute('read_facebook_posts', {'source_page_url': source})
assert read.ok and post in read.text and events[-1] == 'read'
blocked = controller.tools.execute('approve_facebook_campaign', pending['arguments'])
assert not blocked.ok and 'BLOCKED' in blocked.text
assert db.list_rules() == []
'''


def test_arabic_page_lookup_and_group_filter_recover_into_preview(tmp_path):
    result = subprocess.run(
        [sys.executable, "-c", ARABIC_FACEBOOK_FLOW, str(tmp_path / "flow.sqlite3")],
        cwd=Path(__file__).resolve().parents[1], capture_output=True, text=True, timeout=20,
    )
    assert result.returncode == 0, result.stdout + result.stderr
