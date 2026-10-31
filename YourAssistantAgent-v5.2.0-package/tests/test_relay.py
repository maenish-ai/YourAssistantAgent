import base64
from contextlib import contextmanager
import hashlib
import io
import json
from pathlib import Path
import secrets
import threading
import time
from types import SimpleNamespace
import zipfile

import pytest
import requests

from relay_server.server import Broker,RelayServer
from relay_server.setup import configure
from yaa_lite.remote.relay_protocol import RelayKeys,origin,b64
from yaa_lite.remote.relay_bridge import RelayBridge,CHUNK
from yaa_lite.remote.mobile import MobileServer
from yaa_lite.remote.files import RemoteFiles
from yaa_lite.remote.settings import pairing_payload,save_relay_enrollment,load_relay_enrollment
from yaa_lite.security.manager import SecurityManager


def test_python_android_crypto_vector_and_direction_binding():
    from cryptography.hazmat.primitives.ciphers.aead import AESGCM
    keys=RelayKeys('A'*43)
    assert keys.channel=='ec5631b9363f44ff891f50059b369184'
    assert keys.phone_auth=='01gtYqevY0uUgT4MmagzkjM0CoK1sbtbai4NFb1UoCQ'
    assert b64(AESGCM(keys.key).encrypt(bytes(12),b'hello',keys.aad('request','test-request-0001')))=='xcmoYpEA9_xu_a66Kxcx3Aq2p0VI'
    sealed=keys.seal('request','request-00001',{'time':time.time(),'op':'http','args':{}})
    assert keys.open('request',sealed)['op']=='http'
    with pytest.raises(Exception):keys.open('response',sealed)
    damaged=dict(sealed,id='request-00002')
    with pytest.raises(Exception):keys.open('request',damaged)
    damaged=dict(sealed,ciphertext='A'+sealed['ciphertext'][1:])
    if damaged==sealed:damaged['ciphertext']='B'+sealed['ciphertext'][1:]
    with pytest.raises(Exception):keys.open('request',damaged)


@pytest.mark.parametrize('url',['http://public.example','https://name:password@server.example','https://server.example/path','https://server.example?secret=key','https://server.example#fragment'])
def test_no_insecure_or_credentialed_relay_origins(url):
    with pytest.raises(ValueError):origin(url)


def test_enrollment_file_is_encrypted_and_not_in_pairing_qr(tmp_path):
    security=SecurityManager(tmp_path/'security');security.setup('',mode='none')
    enrollment=secrets.token_urlsafe(48);token=secrets.token_urlsafe(32)
    save_relay_enrollment(security,enrollment)
    assert load_relay_enrollment(security)==enrollment
    assert enrollment.encode() not in (security.root/'relay-enrollment.enc').read_bytes()
    payload=pairing_payload('https://relay.example',token)
    assert enrollment not in payload
    assert json.loads(payload)=={'type':'yaa-relay','v':1,'url':'https://relay.example','token':token}
    import qrcode
    image=qrcode.make(payload);buffer=io.BytesIO();image.save(buffer,format='PNG')
    assert buffer.getvalue().startswith(b'\x89PNG')


def test_host_setup_does_not_overwrite_credentials(tmp_path):
    path=configure(tmp_path,'relay.example.com')
    config=json.loads(path.read_text());assert config['relay_url']=='https://relay.example.com'
    assert len(config['enrollment_key'])>=32
    with pytest.raises(ValueError):configure(tmp_path,'other.example.com')
    assert json.loads(path.read_text())==config
    with pytest.raises(ValueError):configure(tmp_path,'https://not-a-domain/path')


class Handler:
    def __init__(self,folder):
        self.files=RemoteFiles(folder);self.messages=[];self.documents=[];self.callbacks=[];self.enabled=True
        self.desktop=SimpleNamespace(frame=lambda:{'image_b64':'fake-private-screen','frame_id':'frame','width':10,'height':10})
    def check_desktop(self):
        if not self.enabled:raise ValueError('disabled')
    def text(self,value):self.messages.append(value)
    def document(self,path,caption):self.documents.append(Path(path).read_bytes());Path(path).unlink()
    def callback(self,value):self.callbacks.append(value)
    def file_import(self,path,folder,name):
        try:self.files.import_file(path,folder,name)
        finally:Path(path).unlink(missing_ok=True)
    def capabilities(self):return {'desktop':True,'files':True}
    def close(self):self.enabled=False


@pytest.fixture
def relay(tmp_path):
    shared=tmp_path/'shared';shared.mkdir()
    handler=Handler(shared);mobile=MobileServer(secrets.token_urlsafe(32),handler,tmp_path/'inbox',port=0)
    mobile.start();key=secrets.token_urlsafe(48);broker=Broker(key);server=RelayServer(('127.0.0.1',0),broker)
    thread=threading.Thread(target=server.serve_forever,daemon=True);thread.start()
    address='http://127.0.0.1:'+str(server.server_address[1])
    bridge=RelayBridge(address,key,mobile._token,mobile,tmp_path/'bridge',local_test=True);bridge.remote.trust_env=False;bridge.start()
    client=requests.Session();client.trust_env=False
    deadline=time.monotonic()+3
    while not bridge.connected and time.monotonic()<deadline:threading.Event().wait(.01)
    assert bridge.connected
    def rpc(op,args,*,identifier=None,envelope=None):
        identifier=identifier or secrets.token_urlsafe(16)
        envelope=envelope or bridge.keys.seal('request',identifier,{'time':time.time(),'op':op,'args':args})
        headers={'Authorization':'Bearer '+bridge.keys.phone_auth}
        sent=client.post(bridge.channel_url+'/requests',headers=headers,json=envelope,timeout=4);assert sent.status_code==202,sent.text
        result=client.get(bridge.channel_url+'/requests/'+identifier,headers=headers,timeout=23)
        assert result.status_code==200,result.text
        opened=bridge.keys.open('response',result.json())
        return opened,envelope
    yield SimpleNamespace(rpc=rpc,bridge=bridge,broker=broker,server=server,client=client,handler=handler,folder=shared,address=address)
    bridge.stop();mobile.stop();server.shutdown();server.server_close();bridge.thread.join(timeout=2);client.close()


def http_args(method,path,body=None):
    return {'method':method,'path':path,'body':b64(json.dumps(body).encode()) if body is not None else ''}


def wait_for(predicate):
    deadline=time.monotonic()+3
    while not predicate() and time.monotonic()<deadline:threading.Event().wait(.01)
    assert predicate()


def test_encrypted_http_requests_and_no_plaintext_at_broker(relay):
    message='owner-private-message-with-sensitive-details'
    response,envelope=relay.rpc('http',http_args('POST','/v1/messages',{'text':message}))
    assert response['ok'] and response['status']==202
    wait_for(lambda:len(relay.handler.messages)==1)
    assert relay.handler.messages==[message]
    assert message not in repr(relay.broker.channels)
    assert message not in json.dumps(envelope)
    assert relay.bridge.token not in repr(relay.broker.channels)
    result,_=relay.rpc('http',http_args('GET','/v1/desktop'))
    assert 'fake-private-screen' in base64.urlsafe_b64decode(result['body']+'='*(-len(result['body'])%4)).decode()
    assert 'fake-private-screen' not in repr(relay.broker.channels)


def test_replayed_rpc_has_no_duplicate_effect_even_after_connector_restart(relay):
    identifier=secrets.token_urlsafe(16)
    args=http_args('POST','/v1/messages',{'text':'run once'})
    first,envelope=relay.rpc('http',args,identifier=identifier)
    wait_for(lambda:len(relay.handler.messages)==1)
    assert relay.bridge.handle(envelope)==relay.bridge.cache[identifier]
    relay.bridge.cache.clear()
    result=relay.bridge.keys.open('response',relay.bridge.handle(envelope))
    assert not result['ok'] and 'already_processed' in result['error']
    assert relay.handler.messages==['run once']
    assert first['status']==202


def test_expired_envelope_and_role_separation(relay):
    keys=relay.bridge.keys;identifier=secrets.token_urlsafe(12)
    expired=keys.seal('request',identifier,{'time':time.time()-1000,'op':'http','args':http_args('POST','/v1/messages',{'text':'no'})})
    result=keys.open('response',relay.bridge.handle(expired));assert 'expired' in result['error']
    assert not relay.handler.messages
    denied=relay.client.post(relay.bridge.channel_url+'/requests',headers={'Authorization':'Bearer '+keys.desktop_auth},json=expired)
    assert denied.status_code==403
    denied=relay.client.get(relay.bridge.channel_url+'/next',headers={'Authorization':'Bearer '+keys.phone_auth})
    assert denied.status_code==403
    denied=relay.client.post(relay.address+'/relay/v1/register',headers={'Authorization':'Bearer '+'x'*43},json={})
    assert denied.status_code==403


def test_chunked_binary_upload_download_and_integrity(relay):
    content=secrets.token_bytes(CHUNK*2+37)
    start,_=relay.rpc('upload_start',{'path':'/v1/files/upload?folder=&name=sample.bin','mime':'application/octet-stream','size':len(content)})
    transfer=start['transfer']
    for offset in range(0,len(content),CHUNK):
        chunk=content[offset:offset+CHUNK]
        result,_=relay.rpc('upload_chunk',{'transfer':transfer,'offset':offset,'data':b64(chunk)})
        assert result['offset']==offset+len(chunk)
    assert not (relay.folder/'sample.bin').exists()
    finish,_=relay.rpc('upload_finish',{'transfer':transfer,'sha256':hashlib.sha256(content).hexdigest()})
    assert finish['status']==202
    wait_for(lambda:(relay.folder/'sample.bin').exists())
    assert (relay.folder/'sample.bin').read_bytes()==content
    download,_=relay.rpc('download_start',{'path':'sample.bin'});received=bytearray()
    while True:
        result,_=relay.rpc('download_chunk',{'transfer':download['transfer'],'offset':len(received)})
        data=base64.urlsafe_b64decode(result['data']+'='*(-len(result['data'])%4));received.extend(data)
        if result['done']:
            assert result['sha256']==hashlib.sha256(received).hexdigest();break
    assert bytes(received)==content
    assert not relay.bridge.transfers
    assert 'sample.bin' not in repr(relay.broker.channels)


def test_bad_transfer_path_size_offset_and_hash_never_write_shared_file(relay):
    result,_=relay.rpc('upload_start',{'path':'https://evil.example','mime':'application/octet-stream','size':10})
    assert not result['ok']
    result,_=relay.rpc('upload_start',{'path':'/v1/uploads','mime':'application/zip','size':21*1024*1024})
    assert not result['ok']
    start,_=relay.rpc('upload_start',{'path':'/v1/files/upload?folder=&name=no.bin','mime':'application/octet-stream','size':3})
    transfer=start['transfer']
    result,_=relay.rpc('upload_chunk',{'transfer':transfer,'offset':1,'data':b64(b'abc')});assert not result['ok']
    relay.rpc('upload_chunk',{'transfer':transfer,'offset':0,'data':b64(b'abc')})
    result,_=relay.rpc('upload_finish',{'transfer':transfer,'sha256':'0'*64})
    assert not result['ok'] and not (relay.folder/'no.bin').exists()
    assert not relay.bridge.transfers
    assert not list(relay.bridge.root.glob('relay-upload-*'))
    result,_=relay.rpc('download_start',{'path':'../outside'});assert not result['ok']


def test_relay_restart_reconnects_same_pairing_without_new_code(relay):
    address=relay.server.server_address
    relay.server.shutdown();relay.server.server_close()
    replacement=RelayServer(address,Broker(relay.bridge.enrollment))
    thread=threading.Thread(target=replacement.serve_forever,daemon=True);thread.start()
    try:
        deadline=time.monotonic()+10
        while relay.bridge.keys.channel not in replacement.broker.channels and time.monotonic()<deadline:
            threading.Event().wait(.03)
        assert relay.bridge.keys.channel in replacement.broker.channels
        result,_=relay.rpc('http',http_args('GET','/v1/capabilities'))
        assert result['ok'] and result['status']==200
    finally:replacement.shutdown();replacement.server_close()


def test_broker_caps_queue_and_rejects_conflicting_reused_ids():
    keys=RelayKeys(secrets.token_urlsafe(32));key=secrets.token_urlsafe(48);broker=Broker(key)
    assert broker.register(key,{'channel':keys.channel,'phone_auth':keys.phone_auth,'desktop_auth':keys.desktop_auth})[0]==200
    info=broker.channels[keys.channel]
    for index in range(32):
        envelope=keys.seal('request','request-id-'+str(index),{'time':time.time(),'op':'http','args':{}})
        assert broker.request(info,envelope)[0]==202
    assert broker.request(info,keys.seal('request','request-id-33',{}))[0]==429
    assert broker.request(info,keys.seal('request','request-id-0',{'changed':True}))[0]==409


def test_zero_byte_file_and_disabled_transfers(relay):
    start,_=relay.rpc('upload_start',{'path':'/v1/files/upload?folder=&name=empty.txt','mime':'application/octet-stream','size':0})
    finish,_=relay.rpc('upload_finish',{'transfer':start['transfer'],'sha256':hashlib.sha256(b'').hexdigest()})
    assert finish['status']==202
    wait_for(lambda:(relay.folder/'empty.txt').exists())
    assert (relay.folder/'empty.txt').read_bytes()==b''
    start,_=relay.rpc('download_start',{'path':'empty.txt'})
    result,_=relay.rpc('download_chunk',{'transfer':start['transfer'],'offset':0})
    assert result['done'] and result['data']=='' and result['sha256']==hashlib.sha256(b'').hexdigest()
    relay.handler.enabled=False
    result,_=relay.rpc('upload_start',{'path':'/v1/files/upload?folder=&name=no.txt','mime':'application/octet-stream','size':3})
    assert not result['ok'] and not relay.bridge.transfers


def test_transient_relay_files_are_not_backed_up(tmp_path,monkeypatch):
    from yaa_lite.backup import crypto_backup
    data=tmp_path/'data';config=tmp_path/'config';config.mkdir();data.mkdir()
    (data/'mobile/inbox').mkdir(parents=True);(data/'mobile/relay').mkdir()
    (data/'mobile/inbox/upload.bin').write_bytes(b'private staging')
    (data/'mobile/relay/relay-upload-file').write_bytes(b'private staging')
    (data/'mobile/conversation.json').write_text('{}')
    monkeypatch.setattr(crypto_backup,'data_dir',lambda:data)
    monkeypatch.setattr(crypto_backup,'config_dir',lambda:config)
    with zipfile.ZipFile(io.BytesIO(crypto_backup._zip_payload())) as archive:
        assert 'data/mobile/conversation.json' in archive.namelist()
        assert not any('/inbox/' in name or '/relay/' in name for name in archive.namelist())


def test_deployment_secret_file_cannot_be_published_in_zip():
    from yaa_lite.github_upload_v430 import _validate_name,GitHubUploadError
    with pytest.raises(GitHubUploadError,match='credential'):_validate_name('relay_server/desktop-setup.json')


def test_invalid_saved_connection_mode_falls_back_safely(tmp_path,monkeypatch):
    from yaa_lite import config
    monkeypatch.setattr(config,'config_dir',lambda:tmp_path)
    (tmp_path/'settings.json').write_text(json.dumps({'remote_connection_mode':[]}))
    assert config.Settings.load().remote_connection_mode=='direct'
