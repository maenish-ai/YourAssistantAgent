"""Owner-mobile conversation tests: actual local Git and exact approval binding."""
from pathlib import Path
from types import SimpleNamespace
import subprocess
import zipfile
import json

import pytest

from yaa_lite.agent.orchestrator import AgentResponse
from yaa_lite.agent.tools import ToolExecution
from yaa_lite.config import Settings
from yaa_lite.github_upload_v430 import GitHubUploadError
from yaa_lite.remote import service as remote
from yaa_lite.review_voice_v270 import permitted_mutation
from yaa_lite.storage.db import ChatDB


@pytest.mark.parametrize('ai_code', [
    'missing_key', 'auth', 'rate_limit', 'network', 'tool_call',
    'invalid_response', 'request_rejected', 'output_limit', 'service_unavailable',
])
def test_tool_failure_has_precise_code_and_discards_partial_plan(conversation, monkeypatch, ai_code):
    from yaa_lite.ai.runtime import LocalAIError
    assistant = conversation.assistant
    assistant.text('draft')
    old_token = conversation.events[-1]['approval_token']

    def fail(*args, **kwargs):
        conversation.db.set_pending_action(assistant.session_id, 'approve_facebook_campaign',
                                           {'plan': {}}, 'Incomplete plan')
        raise LocalAIError('private-token-and-page-content', code=ai_code)

    monkeypatch.setattr(conversation.controller, 'handle', fail)
    assistant.text('جهز آخر إعلان للمجموعات')
    event = conversation.events[-1]
    assert 'groq_' + ai_code in event['text']
    assert event['clear_approval'] and not event['approval_token']
    assert conversation.db.get_pending_action(assistant.session_id) is None
    assistant.callback('approve:' + old_token)
    assert not conversation.controller.executed
    record = next(row for row in conversation.db.recent_activity() if row['kind'] == 'remote_request_error')
    report = json.loads(record['detail'])
    assert report['code'] == 'groq_' + ai_code
    assert any('remote/service.py:' in line for line in report['locations'])
    assert 'private-token-and-page-content' not in str(conversation.events) + record['detail']


def test_diagnostics_does_not_call_ai_or_invalidate_review(conversation, monkeypatch):
    import yaa_lite.ai.runtime as runtime
    assistant = conversation.assistant
    monkeypatch.setattr(runtime, 'get_groq_api_key', lambda required=True: 'private-groq-key')
    assistant.text('draft')
    approval = assistant._approval
    pending = conversation.db.get_pending_action(assistant.session_id)
    calls = len(conversation.controller.calls)
    assistant.text('/diagnostics')
    text = conversation.events[-1]['text']
    assert len(conversation.controller.calls) == calls
    assert assistant._approval is approval
    assert conversation.db.get_pending_action(assistant.session_id) == pending
    assert 'موجود؛ لم يتم اختبار صلاحيته' in text
    assert 'ليس فحصاً مباشراً' in text and 'لم يتم الفحص' in text
    assert 'private-groq-key' not in text


def test_natural_cancellation_clears_preview_without_claiming_schedule_stopped(conversation):
    assistant = conversation.assistant
    assistant.text('draft')
    token = assistant._approval.token
    assistant.text('لا، أنا ما بدي هيك، الغي')
    assert assistant._approval is None
    assert conversation.db.get_pending_action(assistant.session_id) is None
    assert 'المعاينة' in conversation.events[-1]['text']
    assert 'لم أوقف مهمة جارية' in conversation.events[-1]['text']
    assistant.callback('approve:' + token)
    assert not conversation.controller.executed


def test_schedule_can_be_listed_and_disabled_by_exact_id(conversation):
    from yaa_lite.agent.legacy_smart import SmartPlan
    db = conversation.db
    rule_id = db.add_rule(SmartPlan(name='scheduled example', command_text='example', source_page_url='https://www.facebook.com/example'))
    assistant = conversation.assistant
    assistant.text('/tasks')
    assert f'#{rule_id}' in conversation.events[-1]['text']
    assistant.text(f'/pause_task {rule_id}')
    assert db.get_rule(rule_id)['enabled'] == 0
    assert 'لم أحذفها' in conversation.events[-1]['text']


def test_cancel_preview_does_not_silently_disable_saved_task(conversation):
    from yaa_lite.agent.legacy_smart import SmartPlan
    db = conversation.db
    rule_id = db.add_rule(SmartPlan(name='example', command_text='example', source_page_url='https://www.facebook.com/example'))
    conversation.assistant.text('draft')
    conversation.assistant.text('لا، ما بدي، الغي')
    assert db.get_rule(rule_id)['enabled'] == 1
    assert 'لم أوقف مهمة جارية' in conversation.events[-1]['text']


def test_stop_facebook_requests_only_current_run(conversation):
    calls = []
    conversation.facebook.stop_current = lambda: calls.append('stop') or True
    conversation.assistant.text('/stop_facebook')
    assert calls == ['stop']
    assert 'قد تكتمل خطوة' in conversation.events[-1]['text']


def test_programming_error_does_not_blame_groq_or_login(conversation, monkeypatch):
    import yaa_lite.ai.runtime as runtime
    def fail(*args, **kwargs):
        raise TypeError('sensitive request data')
    monkeypatch.setattr(conversation.controller, 'handle', fail)
    monkeypatch.setattr(runtime, 'get_groq_api_key', lambda required=True: '')
    assistant = conversation.assistant
    assistant.text('جهز آخر إعلان للمجموعات')
    text = conversation.events[-1]['text']
    assert 'خطأ برمجي' in text and 'internal_error' in text
    assert 'Groq' not in text and 'تسجيل دخول' not in text
    assistant.text('/diagnostics')
    assert 'internal_error' in conversation.events[-1]['text']
    assert 'غير مضبوط' in conversation.events[-1]['text']
    assert 'sensitive request data' not in str(conversation.events)


@pytest.mark.parametrize('error_class, code', [
    ('LoginRequired', 'facebook_login'), ('CheckpointDetected', 'facebook_checkpoint'),
    ('FacebookError', 'facebook_browser'),
])
def test_facebook_exception_has_own_recovery_message(conversation, monkeypatch, error_class, code):
    from yaa_lite.facebook_backend import facebook
    def fail(*args, **kwargs):
        raise getattr(facebook, error_class)('private browser URL')
    monkeypatch.setattr(conversation.controller, 'handle', fail)
    conversation.assistant.text('جهز آخر إعلان للمجموعات')
    text = conversation.events[-1]['text']
    assert code in text and 'Groq' not in text and 'private browser URL' not in text


def git(directory, *arguments):
    return subprocess.check_output(['git', '-C', str(directory), *arguments], text=True).strip()


class Facebook:
    def __init__(self):
        self.listeners = []
        self.results = {}

    def add_completion_listener(self, listener):
        self.listeners.append(listener)

    def remove_completion_listener(self, listener):
        if listener in self.listeners:
            self.listeners.remove(listener)

    def current_status(self):
        return {'facebook': 'not_checked', 'step': 'idle', 'done': 0, 'total': 0}

    def rule_result(self, identifier):
        return self.results.get(identifier)

    def complete(self, identifier, result):
        self.results[identifier] = result
        for listener in list(self.listeners):
            listener(identifier, result)


class Controller:
    def __init__(self, db):
        self.db = db
        self.calls = []
        self.executed = []
        self.result = ToolExecution(True, 'Task started', {'rule_id': 7, 'run_immediately': True})
        self.tools = SimpleNamespace(execute=self.execute)
        self.on_execute = lambda: None

    def handle(self, profile, history, text, session_id, *args, **kwargs):
        self.calls.append((text, history))
        if text == 'draft':
            self.db.set_pending_action(session_id, 'approve_facebook_campaign',
                                       {'plan': {'post_urls': ['https://www.facebook.com/page/posts/1']}},
                                       'Actual post and exact group preview')
        return AgentResponse('Review before approving' if text == 'draft' else 'No external action executed')

    def execute(self, name, arguments):
        # Exercise the real thread-local execution boundary rather than treating
        # a successful callback as sufficient permission for an arbitrary tool.
        assert permitted_mutation(name, arguments)
        assert not permitted_mutation(name, {'different': True})
        self.executed.append((name, arguments))
        self.on_execute()
        return self.result


@pytest.fixture
def conversation(tmp_path, monkeypatch):
    monkeypatch.setattr('yaa_lite.github_upload_v430.desktop_folder', lambda: tmp_path / 'Desktop')
    db = ChatDB(tmp_path / 'mobile.sqlite3')
    settings = Settings()
    controller = Controller(db)
    facebook = Facebook()
    events = []
    assistant = remote.RemoteAssistant(
        db, settings, None, facebook,
        lambda text, **kwargs: events.append({'text': text, **kwargs}),
        tmp_path / 'remote', controller=controller,
    )
    yield SimpleNamespace(assistant=assistant, db=db, controller=controller,
                          facebook=facebook, events=events, settings=settings)
    assistant.close()


@pytest.fixture
def checkout(tmp_path, conversation):
    directory = tmp_path / 'checkout'
    directory.mkdir()
    git(directory, 'init', '-b', 'main')
    git(directory, 'config', 'user.name', 'Mobile test')
    git(directory, 'config', 'user.email', 'mobile@example.invalid')
    (directory / 'README.md').write_text('before', encoding='utf-8')
    git(directory, 'add', 'README.md')
    git(directory, 'commit', '-m', 'initial')
    git(directory, 'remote', 'add', 'origin', 'https://github.com/maenish-ai/YourAssistantAgent.git')
    conversation.settings.github_repository = 'maenish-ai/YourAssistantAgent'
    conversation.settings.github_checkout = str(directory)
    return directory


def archive(tmp_path):
    path = tmp_path / 'mobile.zip'
    with zipfile.ZipFile(path, 'w') as output:
        output.writestr('README.md', 'after')
        output.writestr('src/new.py', 'print("mobile")\n')
    return path


@pytest.mark.parametrize('instruction', [
    'فك الملف المضغوط على سطح المكتب ثم ارفعه على GitHub',
    'فكيه وارفعيه على GitHub',
])
def test_compound_extract_and_github_request_reaches_desktop_planner(conversation, instruction):
    conversation.settings.remote_desktop_enabled = True
    conversation.settings.remote_ai_enabled = True
    conversation.assistant.text(instruction)
    approval = conversation.assistant._approval
    assert approval is not None
    assert approval.kind == 'desktop_ai'
    assert approval.payload == instruction


def test_plain_github_upload_keeps_review_workflow(conversation):
    conversation.assistant.text('ارفع الملف على GitHub')
    assert conversation.assistant._approval is None
    assert 'مراجعة ZIP' in conversation.events[-1]['text']


def test_explicit_memory_persists_and_can_be_deleted(conversation):
    assistant = conversation.assistant
    assistant.text('تذكري أن اللهجة الشامية هي المفضلة')
    rows = assistant._memory_rows()
    assert len(rows) == 1 and rows[0]['content'] == 'اللهجة الشامية هي المفضلة'
    assistant.text('كيف حالك؟')
    assert 'اللهجة الشامية' in str(conversation.controller.calls[-1][1])
    assistant.text('/memory')
    assert str(rows[0]['id']) in conversation.events[-1]['text']
    assistant.text('/forget ' + str(rows[0]['id']))
    assert not assistant._memory_rows()


def test_memory_respects_settings_and_refuses_obvious_secrets(conversation):
    assistant = conversation.assistant
    assistant.text('/remember API key is private')
    assert not assistant._memory_rows()
    conversation.settings.learning_enabled = False
    assistant.text('/remember أفضل الاختصار')
    assert not conversation.db.list_memory_items()
    assert 'معطلة' in conversation.events[-1]['text']


def test_failure_history_does_not_hide_owner_notes(conversation):
    assistant = conversation.assistant
    assistant.text('/remember أفضل اللهجة الشامية')
    for _ in range(101):
        assistant._record_desktop_failure('desktop_step_failed')
    assistant.text('كيف حالك؟')
    assert 'اللهجة الشامية' in str(conversation.controller.calls[-1][1])


def test_desktop_rate_limit_explains_failure_without_leaking_details(conversation, monkeypatch):
    from yaa_lite.ai.runtime import LocalAIError
    def fail(*args, **kwargs):
        raise LocalAIError('private-response-data', code='rate_limit')
    monkeypatch.setattr('yaa_lite.remote.desktop_agent.run_desktop_task', fail)
    monkeypatch.setattr(conversation.assistant, 'check_desktop', lambda: None)
    conversation.settings.remote_desktop_enabled = True
    conversation.settings.remote_ai_enabled = True
    conversation.assistant.text('افتح نافذة البرنامج')
    conversation.assistant.callback('approve:' + conversation.assistant._approval.token)
    assert 'groq_rate_limit' in conversation.events[-1]['text']
    assert 'private-response-data' not in str(conversation.events)
    conversation.assistant.text('/failures')
    assert 'groq_rate_limit' in conversation.events[-1]['text']
    failure = next(row for row in conversation.db.list_memory_items() if row['kind'] == 'desktop_failure')
    assert 'private-response-data' not in failure['content']
    conversation.assistant.text('/forget_failure ' + str(failure['id']))
    assert not [row for row in conversation.db.list_memory_items() if row['kind'] == 'desktop_failure']


def test_phone_upload_is_passed_to_desktop_planner(conversation, tmp_path, monkeypatch):
    from yaa_lite.remote.files import RemoteFiles
    assistant = conversation.assistant
    shared = tmp_path / 'shared'
    shared.mkdir()
    assistant.files = RemoteFiles(shared)
    monkeypatch.setattr(assistant, 'check_desktop', lambda: None)
    source = tmp_path / 'incoming'
    source.write_bytes(b'file from phone')
    assistant.file_import(source, '', 'incoming.zip')
    assert not source.exists()
    assert (shared / 'incoming.zip').exists()
    received = []
    def execute(*args, **kwargs):
        received.extend(kwargs['phone_uploads'])
        return 'تمت مراجعة الطلب'
    monkeypatch.setattr('yaa_lite.remote.desktop_agent.run_desktop_task', execute)
    conversation.settings.remote_desktop_enabled = True
    conversation.settings.remote_ai_enabled = True
    assistant.text('فكي الملف على الكمبيوتر')
    assistant.callback('approve:' + assistant._approval.token)
    assert [entry['path'] for entry in received] == ['incoming.zip']


def test_zip_review_then_single_approved_real_local_push(conversation, checkout, tmp_path, monkeypatch):
    import yaa_lite.github_upload_v430 as uploads
    assistant = conversation.assistant
    head = git(checkout, 'rev-parse', 'HEAD')
    path = archive(tmp_path)
    assistant.document(path)
    preview = conversation.events[-1]
    token = preview['approval_token']
    assert token and preview['expires_at']
    assert 'README.md' in preview['text'] and 'src/new.py' in preview['text']
    assert git(checkout, 'rev-parse', 'HEAD') == head
    assert (checkout / 'README.md').read_text() == 'before'
    assert not (checkout / 'src/new.py').exists()

    destination = tmp_path / 'published.git'
    subprocess.check_output(['git', 'init', '--bare', str(destination)])
    original = uploads._git
    pushes = []

    def local_push(executable, root, *arguments, **kwargs):
        if arguments[0] == 'push':
            pushes.append(arguments)
            return original(executable, root, 'push', str(destination), *arguments[2:], **kwargs)
        return original(executable, root, *arguments, **kwargs)

    monkeypatch.setattr(uploads, '_git', local_push)
    assistant.callback('approve:' + token)
    assistant.callback('approve:' + token)
    assert len(pushes) == 1
    assert git(destination, 'show', 'main:README.md') == 'after'
    assert git(destination, 'show', 'main:src/new.py') == 'print("mobile")'
    assert not path.exists()
    assert any('Published 2 files' in row['text'] for row in conversation.events)


@pytest.mark.parametrize('instruction', ['change the target', '/new'])
def test_new_text_invalidates_previous_zip_button(conversation, checkout, tmp_path, monkeypatch, instruction):
    path = archive(tmp_path)
    assistant = conversation.assistant
    assistant.document(path)
    token = conversation.events[-1]['approval_token']
    old_session = assistant.session_id
    published = []
    monkeypatch.setattr(remote, 'publish_upload', lambda *args, **kwargs: published.append(True))
    assistant.text(instruction)
    assistant.callback('approve:' + token)
    assert not published
    assert not path.exists()
    assert (checkout / 'README.md').read_text() == 'before'
    if instruction == '/new':
        assert assistant.session_id != old_session


def test_expired_zip_and_cancel_remove_file_without_writes(conversation, checkout, tmp_path, monkeypatch):
    assistant = conversation.assistant
    called = []
    monkeypatch.setattr(remote, 'publish_upload', lambda *args, **kwargs: called.append(True))
    for action in ('expired', 'cancel'):
        path = archive(tmp_path)
        assistant.document(path)
        token = conversation.events[-1]['approval_token']
        if action == 'expired':
            assistant._approval.expires_at = 0
        assistant.callback(('cancel:' if action == 'cancel' else 'approve:') + token)
        assert not path.exists()
    assert not called
    assert (checkout / 'README.md').read_text() == 'before'


def test_failed_publish_consumes_button_and_does_not_retry(conversation, checkout, tmp_path, monkeypatch):
    assistant = conversation.assistant
    path = archive(tmp_path)
    assistant.document(path)
    token = conversation.events[-1]['approval_token']
    attempts = []

    def fail(*args, **kwargs):
        attempts.append(True)
        raise GitHubUploadError('Push failed; local commit remains')

    monkeypatch.setattr(remote, 'publish_upload', fail)
    assistant.callback('approve:' + token)
    assistant.callback('approve:' + token)
    assert len(attempts) == 1
    assert not path.exists()
    assert 'Push failed; local commit remains' in conversation.events[-1]['text']


def test_changed_pending_action_cannot_use_old_facebook_approval(conversation):
    assistant = conversation.assistant
    assistant.text('draft')
    token = conversation.events[-1]['approval_token']
    conversation.db.set_pending_action(assistant.session_id, 'approve_facebook_campaign',
                                       {'plan': {'post_urls': ['https://www.facebook.com/page/posts/2']}},
                                       'Different post')
    assistant.callback('approve:' + token)
    assert not conversation.controller.executed
    assert 'تغيّرت' in conversation.events[-1]['text']
    assert not permitted_mutation('approve_facebook_campaign', {})


def test_facebook_approval_exact_scope_and_completion_before_watch_registration(conversation):
    assistant, facebook = conversation.assistant, conversation.facebook
    result = {'status': 'partial', 'published': 1, 'submitted': 1,
              'pending_approval': 1, 'failed': 1, 'skipped': 2, 'total': 6, 'error': 'One group failed'}
    # Simulate a fast worker finishing before execute_reviewed_action returns.
    conversation.controller.on_execute = lambda: facebook.complete(7, result)
    assistant.text('draft')
    token = conversation.events[-1]['approval_token']
    assistant.callback('approve:' + token)
    assistant.callback('approve:' + token)
    facebook.complete(7, result)
    assert len(conversation.controller.executed) == 1
    replies = [row['text'] for row in conversation.events if 'نتيجة مهمة Facebook #7' in row['text']]
    assert len(replies) == 1
    assert 'partial' in replies[0] and 'بانتظار موافقة الجروب: 1' in replies[0]
    assert 'فشل: 1' in replies[0] and 'One group failed' in replies[0]
    assert conversation.db.get_pending_action(assistant.session_id) is None
    assert not permitted_mutation('approve_facebook_campaign', conversation.controller.executed[0][1])


def test_completion_for_other_tasks_not_sent_and_close_removes_listener(conversation, checkout, tmp_path, monkeypatch):
    assistant, facebook = conversation.assistant, conversation.facebook
    facebook.complete(99, {'status': 'completed', 'published': 99})
    assert not conversation.events
    path = archive(tmp_path)
    assistant.document(path)
    token = conversation.events[-1]['approval_token']
    assistant.close()
    assert not path.exists()
    assert not facebook.listeners
    count = len(conversation.events)
    monkeypatch.setattr(remote, 'publish_upload', lambda *args, **kwargs: pytest.fail('closed callback executed'))
    assistant.callback('approve:' + token)
    assistant.text('draft')
    assert len(conversation.events) == count
    assert not conversation.controller.calls


def test_restart_keeps_chat_history_but_discards_approval(conversation, tmp_path):
    assistant = conversation.assistant
    assistant.text('draft')
    identifier = assistant.session_id
    assert conversation.db.get_pending_action(identifier)
    assistant.close()
    replacement = remote.RemoteAssistant(
        conversation.db, conversation.settings, None, conversation.facebook,
        lambda *args, **kwargs: None, tmp_path / 'remote', controller=conversation.controller,
    )
    assert replacement.session_id == identifier
    assert conversation.db.get_pending_action(identifier) is None
    assert conversation.db.recent_messages('hammer', session_id=identifier)
    replacement.close()


def test_disabled_mobile_builder_does_not_read_credentials_or_start_io(monkeypatch):
    monkeypatch.setattr(remote, 'data_dir', lambda: pytest.fail('disabled service touched filesystem'))
    assert remote.build_remote_worker(Settings(remote_enabled=False), None, None, None, None) is None


def test_typed_yes_for_zip_requires_button_and_keeps_review(conversation, checkout, tmp_path, monkeypatch):
    assistant = conversation.assistant
    path = archive(tmp_path)
    assistant.document(path)
    token = conversation.events[-1]['approval_token']
    attempts = []
    monkeypatch.setattr(remote, 'publish_upload', lambda *args, **kwargs: attempts.append(True) or 'Published')
    assistant.text('نعم')
    assert not attempts
    assert path.exists()
    assert assistant._approval.token == token
    assert not conversation.controller.calls
    assert 'موافق' in conversation.events[-1]['text']
    assistant.callback('approve:' + token)
    assert len(attempts) == 1
    assert not path.exists()


def test_builder_failure_detaches_facebook_listener(conversation, tmp_path, monkeypatch):
    import yaa_lite.remote.mobile as transport
    import yaa_lite.remote.settings as secrets_store
    monkeypatch.setattr(remote, 'data_dir', lambda: tmp_path / 'data')
    monkeypatch.setattr(secrets_store, 'load_remote_token', lambda _: 'A' * 43)
    monkeypatch.setattr(transport, 'MobileServer', lambda *args, **kwargs: (_ for _ in ()).throw(ValueError('bad port')))
    facebook = Facebook()
    # Runtime may be absent: construction does not call the model.
    with pytest.raises(ValueError, match='bad port'):
        remote.build_remote_worker(Settings(remote_enabled=True), None,
                                   conversation.db, None, facebook)
    assert not facebook.listeners


def test_facebook_results_keep_the_originating_chat_after_new_chat(conversation):
    assistant = conversation.assistant
    assistant.text('draft')
    original = assistant.session_id
    token = conversation.events[-1]['approval_token']
    assistant.callback('approve:' + token)
    assistant.text('/new')
    new_session = assistant.session_id
    conversation.facebook.complete(7, {'status': 'completed', 'published': 1, 'total': 1})
    assert any('نتيجة مهمة Facebook #7' in row['content']
               for row in conversation.db.recent_messages('hammer', session_id=original))
    assert not any('نتيجة مهمة Facebook #7' in row['content']
                   for row in conversation.db.recent_messages('hammer', session_id=new_session))


def test_full_preview_is_chunked_with_approval_only_after_every_part(conversation):
    assistant = conversation.assistant
    summary = 'Exact reviewed targets\n' + ('https://www.facebook.com/groups/12345\n' * 2400)
    assistant._offer('facebook', None, 'test-signature', summary)
    events = conversation.events
    assert len(events) > 1
    assert all(not item.get('approval_token') for item in events[:-1])
    assert events[-1]['approval_token']
    assert ''.join(item['text'].split('\n', 1)[1] for item in events) == summary.strip()
    assert all(len(item['text']) < 31000 for item in events)
