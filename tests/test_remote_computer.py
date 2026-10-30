from contextlib import contextmanager
import io
import json
from pathlib import Path
import secrets
import threading
import time
from types import SimpleNamespace
from urllib.parse import quote
from urllib.request import Request, urlopen
from urllib.error import HTTPError

from PIL import Image
import pytest

from yaa_lite.remote.desktop import WindowsDesktop, DesktopError
from yaa_lite.remote.desktop_agent import run_desktop_task
from yaa_lite.remote.files import RemoteFiles, FileError
from yaa_lite.remote.mobile import MobileServer
from yaa_lite.remote.service import RemoteAssistant
from yaa_lite.storage.db import ChatDB
from yaa_lite.config import Settings


@pytest.fixture
def desktop(monkeypatch):
    desktop=WindowsDesktop(lambda: True)
    events=[]
    user=SimpleNamespace(GetSystemMetrics=lambda index: (1920,1080)[index],
                         SetCursorPos=lambda x,y: events.append(('position',x,y)) or True)
    @contextmanager
    def session():yield user
    monkeypatch.setattr(desktop,'_session',session)
    monkeypatch.setattr(desktop,'_check',lambda: None)
    monkeypatch.setattr(desktop,'_send',lambda user,**data: events.append(data))
    desktop._frames['frame']=(1920,1080,time.monotonic())
    return desktop,events


def test_normalized_click_uses_observed_monitor_and_rejects_stale_frame(desktop):
    control,events=desktop
    control.input({'action':'click','frame_id':'frame','x':.5,'y':1})
    assert events==[('position',960,1079),{'flags':2},{'flags':4}]
    control._frames['frame']=(1920,1080,time.monotonic()-20)
    with pytest.raises(DesktopError,match='قديمة'):
        control.input({'action':'click','frame_id':'frame','x':.5,'y':.5})
    assert len(events)==3


@pytest.mark.parametrize('value',[float('nan'),float('inf'),-.1,1.1,True,'0.5'])
def test_invalid_coordinates_never_inject_input(desktop,value):
    control,events=desktop
    with pytest.raises(DesktopError):control.input({'action':'click','frame_id':'frame','x':value,'y':0})
    assert events==[]


def test_arabic_and_surrogate_unicode_and_shortcuts_release_keys(desktop):
    control,events=desktop
    control.input({'action':'text','text':'أ😀'})
    encoded='أ😀'.encode('utf-16-le')
    assert [e['key'] for e in events[::2]]==[int.from_bytes(encoded[i:i+2],'little') for i in range(0,len(encoded),2)]
    assert [e['flags'] for e in events]==[4,6]*3
    events.clear();control.input({'action':'keys','keys':['CTRL','L']})
    assert events==[{'key':17},{'key':76},{'key':76,'flags':2},{'key':17,'flags':2}]
    with pytest.raises(DesktopError):control.input({'action':'keys','keys':['arbitrary command']})


def test_frame_preserves_monitor_geometry_while_bounding_image(desktop,monkeypatch):
    from PIL import ImageGrab
    control,_=desktop
    monkeypatch.setattr(ImageGrab,'grab',lambda **kwargs: Image.new('RGB',(1920,1080)))
    result=control.frame()
    assert result['screen_width']==1920 and result['width']==1280
    assert result['frame_id'] in control._frames
    assert result['image_b64']


def test_file_scope_symlink_and_existing_file_protection(tmp_path):
    shared=tmp_path/'shared';shared.mkdir()
    files=RemoteFiles(shared)
    outside=tmp_path/'outside';outside.mkdir();(outside/'secret.txt').write_text('secret')
    try:(shared/'escape').symlink_to(outside,target_is_directory=True)
    except OSError:pass
    for path in ('../outside/secret.txt','/etc/passwd','C:/secret','folder\\file'):
        with pytest.raises((FileError,FileNotFoundError)):files.resolve(path)
    if (shared/'escape').exists():
        assert not files.listing()['entries']
        with pytest.raises(FileError):files.resolve('escape/secret.txt')
    source=tmp_path/'incoming';source.write_bytes(b'\x00binary\xff')
    assert files.import_file(source,'','sample.bin')['ok']
    assert (shared/'sample.bin').read_bytes()==source.read_bytes()
    with pytest.raises(FileError):files.import_file(source,'','sample.bin')
    with pytest.raises(FileError):files.import_file(source,'','../../escape')
    assert not list(shared.glob('.yaa-upload-*'))


def test_ai_loop_observes_after_click_and_stops_before_unapproved_extra_actions():
    calls=[]
    control=SimpleNamespace(cancel=threading.Event(),observe=lambda: {'window':'browser','elements':[{'id':'real-id','name':'Search'}]},
                            click_element=lambda identifier: calls.append(identifier) or {'ok':True})
    class Runtime:
        n=0
        def native_turn(self,profile,messages,**kwargs):
            self.n+=1
            if self.n==1:
                assert 'real-id' in str(messages)
                return {'tool_calls':[{'name':'click_element','arguments':{'id':'real-id'},'id':'one'}]}
            assert 'observation' in messages[-1]['content']
            return {'content':'The search field was selected.'}
    assert 'selected' in run_desktop_task(Runtime(),control,'select search',lambda message:None)
    assert calls==['real-id']
    class CancelRuntime:
        def native_turn(self,*args,**kwargs):
            control.cancel.set()
            return {'tool_calls':[{'name':'click_element','arguments':{'id':'real-id'}}]}
    run_desktop_task(CancelRuntime(),control,'select search',lambda message:None)
    assert calls==['real-id']


@pytest.fixture
def computer_server(tmp_path):
    settings=Settings(remote_desktop_enabled=True,remote_ai_enabled=True,remote_files_root=str(tmp_path))
    db=ChatDB(tmp_path/'db.sqlite')
    handler=RemoteAssistant(db,settings,None,SimpleNamespace(),lambda *args,**kwargs:None,tmp_path/'state',controller=SimpleNamespace())
    calls=[]
    handler.desktop=SimpleNamespace(frame=lambda:{'frame_id':'screen','image_b64':'test','width':100,'height':50},
        input=lambda value:calls.append(value),cancel=threading.Event(),close=lambda:None)
    token=secrets.token_urlsafe(32)
    server=MobileServer(token,handler,tmp_path/'inbox',port=0);handler.publish=server.publish;server.start()
    def request(path,body=None,mime='application/json',key=None):
        raw=json.dumps(body).encode() if isinstance(body,dict) else body
        headers={'Authorization':'Bearer '+(key or token),'Content-Type':mime,'X-Request-ID':secrets.token_urlsafe(12)}
        try:
            with urlopen(Request(f'http://127.0.0.1:{server.port}'+path,data=raw,headers=headers),timeout=4) as response:
                content=response.read()
                return response.status,json.loads(content) if response.headers.get_content_type()=='application/json' else content
        except HTTPError as error:return error.code,json.loads(error.read())
    yield request,handler,server,calls,tmp_path
    server.stop()


def test_full_authenticated_screen_input_and_bidirectional_binary_transfer(computer_server):
    request,handler,server,calls,folder=computer_server
    assert request('/v1/desktop',key='wrong')[0]==401
    assert request('/v1/desktop')[1]['frame_id']=='screen'
    assert request('/v1/desktop/input',{'action':'keys','keys':['ENTER']})[0]==202
    deadline=time.monotonic()+2
    while not calls and time.monotonic()<deadline:threading.Event().wait(.01)
    assert calls==[{'action':'keys','keys':['ENTER']}]
    payload=b'\x00\x01\xff full file'
    assert request('/v1/files/upload?folder=&name=received.bin',payload,'application/octet-stream')[0]==202
    deadline=time.monotonic()+2
    while not (folder/'received.bin').exists() and time.monotonic()<deadline:threading.Event().wait(.01)
    assert (folder/'received.bin').read_bytes()==payload
    assert request('/v1/files/download?path=received.bin')==(200,payload)
    assert any(e['name']=='received.bin' for e in request('/v1/files')[1]['entries'])
    assert request('/v1/files/download?path=../outside')[0]==400
    handler.settings.remote_desktop_enabled=False
    assert request('/v1/desktop')[0]==400
    assert request('/v1/desktop/input',{'action':'keys','keys':['ENTER']})[0]==400
    assert request('/v1/files')[0]==400


def test_ai_instruction_requires_button_and_stop_invalidates_it(computer_server,monkeypatch):
    from yaa_lite.remote import desktop_agent
    request,handler,server,_,_=computer_server
    called=[]
    monkeypatch.setattr(desktop_agent,'run_desktop_task',lambda *args,**kwargs:called.append(True) or 'Done')
    handler.text('افتح واتساب ويب')
    token=server._events[-1]['token']
    assert not called
    handler.callback('approve:'+token);handler.callback('approve:'+token)
    assert called==[True]
    handler.text('/computer افتح المتصفح')
    token=server._events[-1]['token']
    assert request('/v1/desktop/stop',{})[0]==202
    handler.callback('approve:'+token)
    assert called==[True]


def test_ai_file_offer_returns_owner_download_without_reading_contents(tmp_path):
    private=b'private file contents must not appear in model messages'
    (tmp_path/'report.bin').write_bytes(private)
    files=RemoteFiles(tmp_path); offered=[]
    control=SimpleNamespace(cancel=threading.Event(),observe=lambda:{'window':'Assistant','elements':[]})
    class Runtime:
        n=0
        def native_turn(self,profile,messages,**kwargs):
            assert private.decode() not in str(messages)
            self.n+=1
            if self.n==1:return {'tool_calls':[{'name':'list_files','arguments':{'path':'','contains':'report'},'id':'list'}]}
            if self.n==2:
                assert 'report.bin' in messages[-1]['content']
                return {'tool_calls':[{'name':'send_file_to_phone','arguments':{'path':'report.bin'},'id':'offer'}]}
            assert 'not been saved' in messages[-1]['content']
            return {'content':'A download button is ready.'}
    result=run_desktop_task(Runtime(),control,'send report to my phone',lambda text:None,files=files,
                            offer_download=lambda path,name:offered.append((path,name)))
    assert offered==[('report.bin','report.bin')]
    assert 'ready' in result


def test_empty_file_upload_and_download_event(computer_server):
    request,handler,server,_,folder=computer_server
    assert request('/v1/files/upload?folder=&name=empty.txt',b'','application/octet-stream')[0]==202
    deadline=time.monotonic()+2
    while not (folder/'empty.txt').exists() and time.monotonic()<deadline:threading.Event().wait(.01)
    assert request('/v1/files/download?path=empty.txt')==(200,b'')
    event=server.publish('Ready',download_path='empty.txt',download_name='empty.txt')
    assert event['type']=='file' and event['download_path']=='empty.txt'


def test_keyboard_releases_modifiers_when_second_key_fails(desktop,monkeypatch):
    control,events=desktop
    def send(user,**data):
        events.append(data)
        if data=={'key':76}:raise DesktopError('input failed')
    monkeypatch.setattr(control,'_send',send)
    with pytest.raises(DesktopError):control.input({'action':'keys','keys':['CTRL','L']})
    assert events[-1]=={'key':17,'flags':2}


def test_cancelled_ai_does_not_even_observe_the_desktop():
    cancel=threading.Event();cancel.set()
    desktop=SimpleNamespace(cancel=cancel,observe=lambda:pytest.fail('Cancelled task captured the desktop'))
    assert 'أُوقفت' in run_desktop_task(None,desktop,'open browser',lambda text:None)


def test_desktop_permissions_require_explicit_boolean_opt_in(tmp_path,monkeypatch):
    from yaa_lite import config
    monkeypatch.setattr(config,'config_dir',lambda:tmp_path)
    (tmp_path/'settings.json').write_text(json.dumps({'remote_enabled':True,'remote_desktop_enabled':'false','remote_ai_enabled':True}))
    settings=Settings.load()
    assert settings.remote_enabled
    assert not settings.remote_desktop_enabled and not settings.remote_ai_enabled
