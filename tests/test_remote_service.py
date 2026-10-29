"""Owner-mobile conversation tests: actual local Git and exact approval binding."""
from pathlib import Path
from types import SimpleNamespace
import subprocess
import zipfile

import pytest

from yaa_lite.agent.orchestrator import AgentResponse
from yaa_lite.agent.tools import ToolExecution
from yaa_lite.config import Settings
from yaa_lite.github_upload_v430 import GitHubUploadError
from yaa_lite.remote import service as remote
from yaa_lite.review_voice_v270 import permitted_mutation
from yaa_lite.storage.db import ChatDB


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
def conversation(tmp_path):
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
