"""Exercise the shipped patch stack without a window, account or network."""
from pathlib import Path
import subprocess
import sys

from yaa_lite.storage.db import ChatDB
from yaa_lite.text_first_v300 import chat_context
from yaa_lite.personal_assistant_v220 import _save_selection, _selection_context


def test_context_is_bounded_scoped_and_respects_memory_setting(tmp_path):
    db = ChatDB(tmp_path / 'chat.sqlite3')
    session = db.create_session('hammer')
    other = db.create_session('hammer')
    db.add_message('user', 'other chat secret', 'hammer', other)
    for i in range(20):
        db.add_message('user' if i % 2 == 0 else 'assistant', str(i) + 'x' * 1500, 'hammer', session)
    db.add_message('user', 'current', 'hammer', session)
    context = chat_context(db, session, 'current')
    assert 0 < len(context) <= 12
    assert sum(len(row['content']) for row in context) <= 6000
    assert all('other chat' not in row['content'] and row['content'] != 'current' for row in context)
    _save_selection(db, session, {'include_keywords': ['الفحص']})
    assert 'الفحص' in _selection_context(db, session)
    db.update_session(session, memory_enabled=False)
    assert chat_context(db, session, 'current') == []
    assert _selection_context(db, session) == ''
    assert _selection_context(db, other) == ''


WORKFLOW = r'''
import json
import queue
import sys
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

from yaa_lite.bootstrap import configure_application
configure_application()
from yaa_lite.agent.orchestrator import SmartAgentController
from yaa_lite.config import Settings
from yaa_lite.personal_assistant_v220 import decode_group_filter
from yaa_lite.review_voice_v270 import pending_signature
from yaa_lite.storage.db import ChatDB
from yaa_lite.ui.chat_window import ChatWindow

first = 'اختار الجروبات اللي اسمها الفحص واستثني الفحص التجارية'
second = 'انشر آخر منشور من الصفحة على هالجروبات'
third = 'استثني كمان جروب الفحص الشمالية'

class Runtime:
    index = 0
    def native_turn(self, profile, messages, tools, **kwargs):
        tool_names = {x['function']['name'] for x in tools}
        assert 'open_facebook_login' in tool_names
        index = self.index
        self.index += 1
        if index == 0:
            name, args = 'search_facebook_groups', {'include_keywords': ['الفحص'], 'exclude_names': ['الفحص التجارية']}
        elif index == 1:
            result = json.loads(messages[-1]['content'])
            assert result['count'] == 2
            return {'content': 'اخترت الجروبات المطلوبة', 'tool_calls': []}
        elif index == 2:
            assert any(row['content'] == first for row in messages)
            assert any('Current group selection' in row['content'] for row in messages)
            name, args = 'draft_facebook_campaign', {'run_immediately': True}
        else:
            assert index == 3
            assert any('الخطة الحالية' in row['content'] for row in messages)
            name, args = 'draft_facebook_campaign', {
                'include_keywords': ['الفحص'],
                'exclude_names': ['الفحص التجارية', 'الفحص الشمالية'],
                'run_immediately': True,
            }
        return {'content': '', 'tool_calls': [{'id': 'call' + str(index), 'name': name, 'arguments': args}]}

class Input:
    value = ''
    def get(self, *args): return self.value
    def delete(self, *args): self.value = ''

class Thread:
    def __init__(self, target, **kwargs): self.target = target
    def start(self): self.target()

class Chat:
    def __init__(self, db, controller, settings, session):
        self.db, self.controller, self.settings, self.session_id = db, controller, settings, session
        self.engine = controller.chat_engine
        self.input = Input()
        self.attachments = []
        self.result_q = queue.Queue()
        self.busy = False
        self._v300_mic_active = False
        self._v260_cancel_event = None
        self._v260_serial = 0
        self.on_session_title_changed = None
        self.status = SimpleNamespace(configure=lambda **kwargs: None)
        self.detail_btn = self.detail_box = SimpleNamespace(pack_forget=lambda: None)
    def t(self, ar, en): return ar
    def _append(self, *args): pass
    def _v300_update_buttons(self): pass
    def _v260_cancel(self, **kwargs):
        self._v260_cancel_event.set()
        self._v260_cancel_event = None
    def after(self, *args): pass
    def send(self, text):
        self.input.value = text
        with patch('threading.Thread', Thread):
            ChatWindow.send(self)
        replies = []
        while not self.result_q.empty():
            kind, serial, value = self.result_q.get_nowait()
            assert kind != 'ai_error', value
            if kind == 'reply': replies.append(value)
        assert len(replies) == 1
        self.db.add_message('assistant', replies[0].text, 'hammer', self.session_id)
        self.busy = False
        self._v260_cancel_event = None
        return replies[0]

db = ChatDB(Path(sys.argv[1]))
session = db.create_session('hammer')
db.upsert_groups([
    {'name': 'الفحص', 'url': 'https://www.facebook.com/groups/1'},
    {'name': 'الفحص الشمالية', 'url': 'https://www.facebook.com/groups/2'},
    {'name': 'الفحص التجارية', 'url': 'https://www.facebook.com/groups/3'},
])
settings = Settings(default_source_page='https://www.facebook.com/testpage')
runtime = Runtime()
engine = SimpleNamespace(runtime=runtime)
controller = SmartAgentController(db, settings, engine, SimpleNamespace())
chat = Chat(db, controller, settings, session)
assert chat.send(first).used_tools
assert db.get_pending_action(session) is None
assert chat.send(second).used_tools
pending = db.get_pending_action(session)
assert pending['tool_name'] == 'approve_facebook_campaign'
spec = decode_group_filter(pending['arguments']['plan']['group_keyword'])
assert spec['include_keywords'] == ['الفحص']
assert spec['exclude_names'] == ['الفحص التجارية']
assert len(db.list_groups(keyword=pending['arguments']['plan']['group_keyword'])) == 2
old_signature = pending_signature(pending)
assert chat.send(third).used_tools
pending = db.get_pending_action(session)
assert pending_signature(pending) != old_signature
assert len(db.list_groups(keyword=pending['arguments']['plan']['group_keyword'])) == 1
reply = chat.send('نعم')
assert 'زر' in reply.text
assert runtime.index == 4  # Typed approval never reaches the model or a publishing tool.
assert db.list_rules() == []
assert db.get_pending_action(session) is not None
'''


def test_two_turn_selection_draft_edit_and_typed_approval(tmp_path):
    completed = subprocess.run(
        [sys.executable, '-c', WORKFLOW, str(tmp_path / 'workflow.sqlite3')],
        cwd=Path(__file__).resolve().parents[1], capture_output=True, text=True, timeout=15,
    )
    assert completed.returncode == 0, completed.stdout + completed.stderr
