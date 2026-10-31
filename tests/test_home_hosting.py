import json
from pathlib import Path
import secrets
import socket
import threading
from types import SimpleNamespace
import pytest
import requests
from yaa_lite.remote.home import identity,tls_context,pairing_payload,KEY_FILE,CERT_FILE
from yaa_lite.remote.mobile import MobileServer,MobileServerError
from yaa_lite.security.manager import SecurityManager


@pytest.fixture
def security(tmp_path):
    value=SecurityManager(tmp_path/'security');value.setup('',mode='none');return value


def test_private_identity_is_encrypted_persistent_and_qr_contains_only_public_identity(security):
    first,pem=identity(security);second,_=identity(security)
    assert first.serial_number==second.serial_number
    assert b'PRIVATE KEY' not in (security.root/KEY_FILE).read_bytes()
    assert pem not in (security.root/KEY_FILE).read_bytes()
    token=secrets.token_urlsafe(32)
    code=json.loads(pairing_payload(security,token,8443,'https://computer.example:8443','https://192.168.1.10:8443'))
    assert code['urls']==['https://192.168.1.10:8443','https://computer.example:8443']
    assert code['type']=='yaa-direct' and len(code['cert_sha256'])==64
    assert 'PRIVATE KEY' not in json.dumps(code)
    assert not list(security.root.glob('*.key'))


def test_public_plain_http_listener_is_never_allowed(tmp_path):
    with pytest.raises(MobileServerError,match='HTTPS'):
        MobileServer('A'*43,SimpleNamespace(),tmp_path,port=0,bind='0.0.0.0')


def test_application_factory_hosts_https_without_relay_configuration(security,tmp_path,monkeypatch):
    from yaa_lite.config import Settings
    from yaa_lite.remote import service
    from yaa_lite.remote.home import HomeWorker
    from yaa_lite.remote.settings import save_remote_token
    token=secrets.token_urlsafe(32);save_remote_token(security,token)
    handler=SimpleNamespace(capabilities=lambda:{'desktop':False},close=lambda:None)
    monkeypatch.setattr(service,'RemoteAssistant',lambda *a,**k:handler)
    monkeypatch.setattr(service,'data_dir',lambda:tmp_path)
    settings=Settings(remote_enabled=True,remote_connection_mode='home',remote_home_port=0)
    worker=service.build_remote_worker(settings,security,None,None,None)
    assert isinstance(worker,HomeWorker) and worker.server.tls_context is not None
    worker.start();session=requests.Session();session.trust_env=False
    try:
        response=session.get('https://127.0.0.1:'+str(worker.server.port)+'/v1/capabilities',
            headers={'Authorization':'Bearer '+token},verify=str(security.root/CERT_FILE),timeout=3)
        assert response.status_code==200 and response.json()=={'desktop':False}
    finally:session.close();worker.stop()


def test_live_personal_https_auth_and_stalled_handshake_do_not_block_other_clients(security,tmp_path):
    received=[];context,_=tls_context(security);token=secrets.token_urlsafe(32)
    handler=SimpleNamespace(capabilities=lambda:{'desktop':False,'files':True},text=received.append,close=lambda:None)
    server=MobileServer(token,handler,tmp_path/'inbox',port=0,bind='0.0.0.0',tls_context=context)
    server.start();session=requests.Session();session.trust_env=False
    base='https://127.0.0.1:'+str(server.port)
    stalled=socket.create_connection(('127.0.0.1',server.port),timeout=2)
    try:
        kwargs={'verify':str(security.root/CERT_FILE),'timeout':3}
        assert session.get(base+'/v1/capabilities',**kwargs).status_code==401
        headers={'Authorization':'Bearer '+token}
        assert session.get(base+'/v1/capabilities',headers=headers,**kwargs).json()['files']
        assert session.get(base+'/v1/capabilities',headers={**headers,'Origin':'https://untrusted.example'},**kwargs).status_code==403
        headers['X-Request-ID']='self-host-request-123'
        assert session.post(base+'/v1/messages',headers=headers,json={'text':'hello directly'},**kwargs).status_code==202
        assert session.post(base+'/v1/messages',headers=headers,json={'text':'hello directly'},**kwargs).json()['duplicate']
        for _ in range(100):
            if received:break
            threading.Event().wait(.01)
        assert received==['hello directly']
        with pytest.raises(requests.exceptions.SSLError):
            session.get(base+'/v1/capabilities',headers=headers,timeout=3)
    finally:
        stalled.close();session.close();server.stop()


@pytest.fixture
def home_view(security,monkeypatch):
    import tkinter as tk
    from yaa_lite.config import Settings
    from yaa_lite.ui.app import App
    from yaa_lite.ui.settings_view import SettingsView
    monkeypatch.setattr(Settings,'save',lambda s:None)
    try:root=tk.Tk()
    except tk.TclError:pytest.skip('Tk display unavailable')
    root.geometry('1100x800');App._styles(root);calls=[]
    view=SettingsView(root,Settings(interface_language='en'),calls.append,security,remote_status=lambda:'Home test')
    view.pack(fill='both',expand=True);view.show_category('pairing');root.update()
    try:yield view,root,calls
    finally:view.destroy();root.destroy()


def test_home_pairing_needs_no_relay_or_external_account_and_shows_real_qr(home_view):
    view,root,calls=home_view
    assert 'Home hosting is stopped' in view._remote_status_label.cget('text')
    view.vars['remote_home_lan_url'].set('https://192.168.1.10:8443')
    view.vars['remote_desktop_enabled'].set(True)
    view.save();root.update()
    assert calls[-1].remote_enabled and calls[-1].remote_connection_mode=='home'
    assert not calls[-1].remote_relay_url
    assert any(child.cget('image') for child in view._qr_panel.winfo_children())
    view._disable_phone();assert not calls[-1].remote_enabled


def test_qr_is_not_shown_when_real_app_reports_server_start_failure(home_view):
    view,root,calls=home_view
    view.remote_ready=lambda:False
    view.vars['remote_home_lan_url'].set('https://192.168.1.10:8443')
    view.save();root.update()
    assert not any(child.cget('image') for child in view._qr_panel.winfo_children())
    assert 'did not start' in view.status.cget('text')


def test_full_access_pairing_saves_real_desktop_ai_drive_and_awake_permissions(home_view):
    view,root,calls=home_view
    view.vars['remote_home_lan_url'].set('https://192.168.1.10:8443')
    assert not view.settings.remote_desktop_enabled
    view._full_access_pairing();root.update()
    saved=calls[-1]
    assert saved.remote_enabled and saved.remote_desktop_enabled and saved.remote_ai_enabled
    assert saved.remote_files_all_drives and saved.remote_keep_awake
    assert any(child.cget('image') for child in view._qr_panel.winfo_children())
