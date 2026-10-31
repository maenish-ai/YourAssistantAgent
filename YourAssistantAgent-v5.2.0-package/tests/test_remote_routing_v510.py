"""Exercise phone routing through the actual configured controller stack."""
from types import SimpleNamespace
from pathlib import Path
import subprocess
import sys

import pytest

from yaa_lite.agent.facebook_service import FacebookActionResult
from yaa_lite.config import Settings
from yaa_lite.remote.home import connection_scope
from yaa_lite.remote.service import RemoteAssistant
from yaa_lite.storage.db import ChatDB


@pytest.mark.parametrize('command', [
    'افتح فيسبوك', 'فوت عالفيسبوك', 'افتح متصفح على الفيسبوك',
    'افتح براوزر على الديسكتوب وفوت على فيسبوك',
    'افتح facebook.com',
])
def test_phone_opens_managed_facebook_without_default_browser_or_model(tmp_path, command):
    # Bootstrap patches are process-global. Exercise the shipped app in a fresh
    # process so legacy unpatched-controller tests retain their own contract.
    script = r'''
from pathlib import Path
from types import SimpleNamespace
import sys
from yaa_lite.bootstrap import configure_application
configure_application()
from yaa_lite.agent.facebook_service import FacebookActionResult
from yaa_lite.config import Settings
from yaa_lite.remote.service import RemoteAssistant
from yaa_lite.storage.db import ChatDB
calls=[]
facebook=SimpleNamespace(open_manual_login=lambda:calls.append('controlled-profile') or FacebookActionResult(True,'فتحت متصفح التحكم'))
def unexpected(*a, **kw): raise AssertionError('Simple open must not use the model')
events=[]
root=Path(sys.argv[1])
assistant=RemoteAssistant(ChatDB(root/'db.sqlite'),Settings(),SimpleNamespace(native_turn=unexpected),facebook,lambda text,**kw:events.append(text),root/'state')
try:
    assistant.text(sys.argv[2])
    assert calls == ['controlled-profile']
    assert assistant._approval is None
    assert events[-1] == 'فتحت متصفح التحكم'
finally: assistant.close()
'''
    result=subprocess.run([sys.executable,'-c',script,str(tmp_path),command],
        cwd=Path(__file__).resolve().parents[1],capture_output=True,text=True,timeout=20)
    assert result.returncode == 0, result.stdout + result.stderr


@pytest.mark.parametrize('command', [
    'افتح فيسبوك وانشر آخر إعلان على المجموعات',
    'افتح براوزر على فيسبوك واقرأ آخر منشور',
    'افتح متصفح النشر',
])
def test_compound_facebook_tasks_use_controller_not_generic_desktop(tmp_path, command):
    calls = []
    controller = SimpleNamespace(handle=lambda *a, **kw: calls.append(a[2]) or SimpleNamespace(text='خطة فيسبوك'))
    assistant = RemoteAssistant(ChatDB(tmp_path/'db.sqlite'),
        Settings(remote_desktop_enabled=True, remote_ai_enabled=True), None, SimpleNamespace(),
        lambda *a, **kw: None, tmp_path/'state', controller=controller)
    try:
        assistant.text(command)
        assert calls == [command] and assistant._approval is None
    finally:
        assistant.close()


@pytest.mark.parametrize('public,fragment', [
    ('', 'لم يُضبط عنوان خارجي'),
    ('https://192.168.1.10:8443', 'ليس عنواناً عاماً'),
    ('https://100.64.10.5:8443', 'ليس عنواناً عاماً'),
    ('https://localhost:8443', 'محلي فقط'),
    ('https://computer.local:8443', 'محلي فقط'),
    ('https://owner.example:8443', 'الوصول غير مُختبر'),
    ('https://[2606:4700::1234]:8443', 'الوصول غير مُختبر'),
    ('http://owner.example', 'غير صالح'),
])
def test_home_configuration_never_claims_internet_connectivity_without_probe(public, fragment):
    settings = Settings(remote_connection_mode='home', remote_home_public_url=public)
    assert fragment in connection_scope(settings)


def test_approved_desktop_history_reaches_followup_and_new_chat_clears_it(tmp_path, monkeypatch):
    histories = []
    def execute(runtime, desktop, instruction, publish, **kwargs):
        histories.append(kwargs['history'])
        return 'أُرسل الإجراء إلى النافذة'
    monkeypatch.setattr('yaa_lite.remote.desktop_agent.run_desktop_task', execute)
    assistant = RemoteAssistant(ChatDB(tmp_path/'db.sqlite'),
        Settings(remote_desktop_enabled=True, remote_ai_enabled=True), None, SimpleNamespace(),
        lambda *a, **kw: None, tmp_path/'state',
        controller=SimpleNamespace(handle=lambda *a, **kw: pytest.fail('Wrong executor')))
    monkeypatch.setattr(assistant, 'check_desktop', lambda: None)
    try:
        assistant.text('افتح GitHub')
        assert not histories
        assistant.callback('approve:' + assistant._approval.token)
        assistant.text('أغلقها')
        assistant.callback('approve:' + assistant._approval.token)
        assert histories[0] == []
        assert histories[1][0]['instruction'] == 'افتح GitHub'
        assistant.text('/new')
        assert assistant._desktop_history == []
    finally:
        assistant.close()
