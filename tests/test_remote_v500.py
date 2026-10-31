from contextlib import contextmanager
import json
import secrets
import threading
import time
from types import SimpleNamespace
from urllib.error import HTTPError
from urllib.request import Request,urlopen

import pytest
from yaa_lite.config import Settings
from yaa_lite.remote.desktop import WindowsDesktop,DesktopError
from yaa_lite.remote.desktop_agent import run_desktop_task
from yaa_lite.remote.desktop_intent import direct_task,is_desktop_request
from yaa_lite.remote.mobile import MobileServer,MAX_AUDIO_BYTES
from yaa_lite.remote.service import RemoteAssistant
from yaa_lite.storage.db import ChatDB


@pytest.mark.parametrize('text',['سكّر الصفحات','اخرج من الصفحات اللي فتحناها','أغلق النافذة','سكرلي التبويب','فوت على صفحة satellite','close this window'])
def test_open_and_close_are_computer_requests(text):assert is_desktop_request(text)


@pytest.mark.parametrize('text',['هذا مثال فقط افتح المتصفح','لا تنفذ اغلق النافذة','اشرح لي كيف أغلق النافذة','مستوى السكر مرتفع'])
def test_examples_and_explanations_are_not_commands(text):assert not is_desktop_request(text)


def test_open_exact_url_does_not_depend_on_accessibility_or_model():
    calls=[]
    desktop=SimpleNamespace(cancel=threading.Event(),observe=lambda:pytest.fail('Unnecessary UIA dependency'),
        open_url=lambda url:calls.append(url) or {'result':'Opening requested'})
    result=run_desktop_task(None,desktop,'افتح https://example.test/CaseSensitive?q=A!',lambda *_:None)
    assert calls==['https://example.test/CaseSensitive?q=A!'] and result=='Opening requested'
    assert 'google.com/search' in direct_task('افتح صفحة satellite')[1]['url']
    assert direct_task('افتح https://example.test ثم اغلق النافذة') is None


def test_current_tab_and_window_closing_reach_actual_tools_without_model():
    calls=[]
    desktop=SimpleNamespace(cancel=threading.Event(),browser_action=lambda **kw:calls.append(kw) or {'ok':True},
        list_windows=lambda:{'windows':[{'id':'actual-window','active':True,'title':'Editor'}]},
        window_action=lambda *args:calls.append(args) or {'ok':True})
    run_desktop_task(None,desktop,'سكر التبويب',lambda *_:None)
    run_desktop_task(None,desktop,'أغلق النافذة',lambda *_:None)
    assert calls==[{'action':'close_tab'},('actual-window','close')]


def test_inaccessible_active_window_does_not_disable_other_desktop_tools():
    actions=[]
    def unavailable():raise DesktopError('UIA not available')
    desktop=SimpleNamespace(cancel=threading.Event(),observe=unavailable,
        list_windows=lambda:{'windows':[{'id':'real','title':'Browser'}]},
        window_action=lambda identifier,action:actions.append((identifier,action)) or {'ok':True})
    class Runtime:
        step=0
        def native_turn(self,*args,**kwargs):
            self.step+=1
            if self.step==1:return {'tool_calls':[{'name':'list_windows','arguments':{'offset':0},'id':'a'}]}
            if self.step==2:return {'tool_calls':[{'name':'window_action','arguments':{'id':'real','action':'close'},'id':'b'}]}
            return {'content':'Close requested'}
    assert run_desktop_task(Runtime(),desktop,'اغلق نافذة Browser',lambda *_:None)=='Close requested'
    assert actions==[('real','close')]


def test_observed_window_ids_expire_and_changed_process_never_gets_input(monkeypatch):
    desktop=WindowsDesktop(lambda:True);events=[];foreground=[123]
    window=SimpleNamespace(handle=123,window_text=lambda:'Browser',process_id=lambda:999999,
        is_visible=lambda:True,is_minimized=lambda:False,set_focus=lambda:events.append('focus'))
    user=SimpleNamespace(GetForegroundWindow=lambda:foreground[0])
    @contextmanager
    def session():yield user
    monkeypatch.setattr(desktop,'_session',session)
    monkeypatch.setattr(desktop,'_enumerate_windows',lambda:[window])
    monkeypatch.setattr(desktop,'_process_image',lambda _: 'msedge.exe')
    row=desktop.list_windows()['windows'][0]
    assert row['active'] and row['process']=='msedge.exe'
    desktop.window_action(row['id'],'focus');assert events==['focus']
    window.process_id=lambda:888888
    with pytest.raises(DesktopError):desktop.window_action(row['id'],'focus')
    assert events==['focus']
    window.process_id=lambda:999999
    entry=desktop._windows[row['id']];desktop._windows[row['id']]=(entry[0],entry[1],time.monotonic()-100,entry[3])
    with pytest.raises(DesktopError):desktop.window_action(row['id'],'focus')


@pytest.fixture
def remote(tmp_path):
    db=ChatDB(tmp_path/'db.sqlite');events=[]
    settings=Settings(remote_desktop_enabled=True,remote_ai_enabled=True)
    controller=SimpleNamespace(handle=lambda *a,**k:pytest.fail('Desktop request fell through to chat refusal'))
    handler=RemoteAssistant(db,settings,None,SimpleNamespace(),lambda text,**kw:events.append({'text':text,**kw}),tmp_path/'state',controller=controller)
    token=secrets.token_urlsafe(32);server=MobileServer(token,handler,tmp_path/'inbox',port=0);handler.publish=server.publish;server.start()
    def request(path,body=None,mime='application/json',identifier=None,auth=None,length=None):
        payload=json.dumps(body).encode() if isinstance(body,dict) else body
        headers={'Authorization':'Bearer '+(auth or token),'Content-Type':mime,'X-Request-ID':identifier or secrets.token_urlsafe(16)}
        if length is not None:headers['Content-Length']=str(length)
        try:
            with urlopen(Request('http://127.0.0.1:'+str(server.port)+path,data=payload,headers=headers),timeout=4) as response:return response.status,json.loads(response.read())
        except HTTPError as exc:return exc.code,json.loads(exc.read())
    yield handler,server,request
    server.stop()


def test_close_request_routes_to_phone_review_and_executes_once(remote):
    handler,server,_=remote;calls=[]
    handler.desktop.browser_action=lambda **kw:calls.append(kw) or {'ok':True}
    handler.text('سكر التبويب')
    approval=server._events[-1]['token'];assert not calls
    handler.callback('approve:'+approval);handler.callback('approve:'+approval)
    assert calls==[{'action':'close_tab'}]
    handler.text('هذا مثال فقط اغلق النافذة');assert len(calls)==1 and handler._approval is None


def test_audio_is_authenticated_deduplicated_deleted_and_only_returned_as_dictation(remote,monkeypatch):
    from yaa_lite.voice.cloud_service import CloudVoiceService
    handler,server,request=remote;calls=[]
    def transcribe(self,path,**kwargs):calls.append((path,kwargs));return 'اغلق النافذة'
    monkeypatch.setattr(CloudVoiceService,'transcribe_file',transcribe)
    payload=b'\x00\x00\x00\x18ftypM4A test-only-audio'
    path='/v1/dictation?id=owner-recording-123'
    assert request(path,payload,'audio/mp4',auth='wrong')[0]==401
    assert request(path,payload,'audio/mp4',identifier='same-audio-request-123')[0]==202
    assert request(path,payload,'audio/mp4',identifier='same-audio-request-123')[1]['duplicate']
    deadline=time.monotonic()+2
    while not server._events and time.monotonic()<deadline:threading.Event().wait(.01)
    event=server._events[-1]
    assert event['type']=='dictation' and event['dictation_text']=='اغلق النافذة'
    assert event['dictation_id']=='owner-recording-123' and 'token' not in event
    assert len(calls)==1 and calls[0][1]=={'mime':'audio/mp4'}
    deadline=time.monotonic()+2
    while list(server.inbox.glob('*.m4a')) and time.monotonic()<deadline:threading.Event().wait(.01)
    assert not list(server.inbox.glob('*.m4a')) and handler._approval is None


def test_audio_error_never_turns_into_an_instruction_and_bad_audio_is_rejected(remote,monkeypatch):
    from yaa_lite.voice.cloud_service import CloudVoiceService
    handler,server,request=remote
    monkeypatch.setattr(CloudVoiceService,'transcribe_file',lambda *a,**k:(_ for _ in ()).throw(RuntimeError('do not leak key')))
    assert request('/v1/dictation?id=recording-123',b'not an MP4','audio/mp4')[0]==400
    assert not list(server.inbox.glob('*.m4a'))
    assert request('/v1/dictation?id=recording-123',b'x','audio/mp4',length=MAX_AUDIO_BYTES+1)[0]==413
    assert request('/v1/dictation?id=recording-123',b'1234ftypM4A audio','audio/mp4')[0]==202
    deadline=time.monotonic()+2
    while not server._events and time.monotonic()<deadline:threading.Event().wait(.01)
    event=server._events[-1]
    assert event['type']=='dictation' and event.get('dictation_error') and not event.get('dictation_text')
    assert 'do not leak key' not in json.dumps(event) and handler._approval is None


def test_window_api_needs_existing_desktop_permission(remote):
    handler,server,request=remote;calls=[]
    handler.desktop.list_windows=lambda:{'windows':[{'id':'window-id-123','title':'Browser'}]}
    handler.desktop.window_action=lambda *args:calls.append(args) or {'ok':True}
    assert request('/v1/windows')[1]['windows'][0]['id']=='window-id-123'
    assert request('/v1/windows/action',{'id':'window-id-123','action':'focus'})[0]==202
    deadline=time.monotonic()+2
    while not calls and time.monotonic()<deadline:threading.Event().wait(.01)
    assert calls==[('window-id-123','focus')]
    handler.settings.remote_desktop_enabled=False
    assert request('/v1/windows')[0]==400
    assert request('/v1/windows/action',{'id':'window-id-123','action':'close'})[0]==400


def test_dictation_does_not_wait_behind_a_running_computer_task(remote,monkeypatch):
    from yaa_lite.voice.cloud_service import CloudVoiceService
    handler,server,request=remote;entered=threading.Event();release=threading.Event()
    def long_task(text):entered.set();release.wait(4)
    monkeypatch.setattr(handler,'text',long_task)
    monkeypatch.setattr(CloudVoiceService,'transcribe_file',lambda *a,**k:'نص للمراجعة')
    try:
        assert request('/v1/messages',{'text':'long desktop task'})[0]==202
        assert entered.wait(1)
        assert request('/v1/dictation?id=concurrent-audio-123',b'1234ftypM4A audio','audio/mp4')[0]==202
        deadline=time.monotonic()+2
        while not server._events and time.monotonic()<deadline:threading.Event().wait(.01)
        assert server._events[-1]['dictation_text']=='نص للمراجعة' and not release.is_set()
    finally:release.set()
