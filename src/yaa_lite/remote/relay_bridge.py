"""Outbound desktop connector; no incoming router port or VPN is needed."""
from __future__ import annotations
from collections import OrderedDict
import base64
import hashlib
import json
import os
from pathlib import Path
import secrets
import sqlite3
import tempfile
import threading
import time
from urllib.parse import urlsplit,parse_qs
import requests
from .relay_protocol import RelayKeys,origin,b64,unb64
from .files import MAX_TRANSFER

CHUNK=512*1024


class RelayBridge:
    def __init__(self,url,enrollment,token,server,root,*,local_test=False):
        self.url=origin(url,local_test=local_test)
        if not isinstance(enrollment,str) or not 32<=len(enrollment)<=256:raise ValueError('Set a valid relay enrollment key')
        self.enrollment=enrollment;self.token=token;self.keys=RelayKeys(token);self.server=server
        self.root=Path(root);self.root.mkdir(parents=True,exist_ok=True)
        for old in self.root.glob('relay-upload-*'):
            if old.is_file() and not old.is_symlink() and time.time()-old.stat().st_mtime>86400:old.unlink(missing_ok=True)
        self.stop_event=threading.Event();self.thread=None;self.connected=False;self._state='waiting'
        self.remote=requests.Session();self.local=requests.Session();self.local.trust_env=False
        self.cache=OrderedDict();self.transfers={}
        self.database=self.root/'relay-replay.sqlite3'
        with sqlite3.connect(self.database) as db:db.execute('CREATE TABLE IF NOT EXISTS seen(channel TEXT,id TEXT,created REAL,PRIMARY KEY(channel,id))')

    def start(self):
        if self.thread and self.thread.is_alive():return
        self.thread=threading.Thread(target=self._loop,daemon=True,name='yaa-outbound-relay');self.thread.start()

    def status_text(self):
        return {'waiting':'جارٍ الاتصال بخادم الإقران…','connected':'خادم الإقران متصل — يمكن مسح QR من الهاتف',
                'denied':'الخادم رفض مفتاح التسجيل. راجع إعداد الاستضافة.',
                'retry':'انقطع اتصال الخادم. إعادة الاتصال تلقائية…','stopped':'الاتصال التلقائي متوقف'}.get(self._state,'جارٍ الاتصال…')

    def _headers(self,role):return {'Authorization':'Bearer '+getattr(self.keys,role+'_auth')}
    @property
    def channel_url(self):return self.url+'/relay/v1/'+self.keys.channel

    def _loop(self):
        while not self.stop_event.is_set():
            try:
                registration=self.remote.post(self.url+'/relay/v1/register',headers={'Authorization':'Bearer '+self.enrollment},
                    json={'channel':self.keys.channel,'desktop_auth':self.keys.desktop_auth,'phone_auth':self.keys.phone_auth},timeout=(10,20),allow_redirects=False)
                status=registration.status_code;registration.close()
                if status!=200:
                    self._state='denied' if status in (401,403) else 'retry'
                    self.stop_event.wait(5);continue
                self.connected=True;self._state='connected'
                while not self.stop_event.is_set():
                    with self.remote.get(self.channel_url+'/next',headers=self._headers('desktop'),timeout=(10,23),allow_redirects=False) as response:
                        response.raise_for_status();envelope=response.json().get('request')
                    self._cleanup()
                    if not envelope:continue
                    if self.stop_event.is_set():break
                    result=self.handle(envelope)
                    if self.stop_event.is_set():break
                    with self.remote.post(self.channel_url+'/response/'+envelope['id'],headers=self._headers('desktop'),json=result,timeout=(10,20),allow_redirects=False) as posted:
                        if posted.status_code not in (200,404):raise ValueError('Unexpected relay response')
            except Exception:
                self._state='retry';self.connected=False
                self.stop_event.wait(3)
        self.connected=False;self._state='stopped'
        self._cleanup(all_transfers=True)
        self.remote.close();self.local.close()

    def handle(self,envelope):
        # Authentication/decryption comes before any parsing or local action.
        value=self.keys.open('request',envelope);identifier=envelope['id'];now=time.time()
        stamp=value.get('time')
        if isinstance(stamp,bool) or not isinstance(stamp,(int,float)) or not now-300<=stamp<=now+120:
            return self.keys.seal('response',identifier,{'ok':False,'error':'request_expired_check_phone_clock'})
        if identifier in self.cache:return self.cache[identifier]
        with sqlite3.connect(self.database) as db:
            db.execute('DELETE FROM seen WHERE created<?',(now-700,))
            try:db.execute('INSERT INTO seen VALUES(?,?,?)',(self.keys.channel,identifier,now))
            except sqlite3.IntegrityError:
                return self.keys.seal('response',identifier,{'ok':False,'error':'request_already_processed_check_conversation'})
        try:
            if self.stop_event.is_set():raise ValueError('connection_stopped')
            result=self._dispatch(identifier,value)
            result={'ok':True,**result}
        except Exception as exc:
            # No request-library exceptions/credentials are forwarded.
            result={'ok':False,'error':str(exc)[:160] if isinstance(exc,ValueError) else 'desktop_operation_failed_check_conversation'}
        encrypted=self.keys.seal('response',identifier,result)
        self.cache[identifier]=encrypted
        while len(self.cache)>32:self.cache.popitem(last=False)
        return encrypted

    def _path(self,path):
        if not isinstance(path,str) or not path.startswith('/v1/') or len(path)>4096 or any(c in path for c in ('\r','\n','\\','#')):raise ValueError('invalid_api_path')
        parsed=urlsplit(path)
        if parsed.scheme or parsed.netloc or '..' in parsed.path.split('/'):raise ValueError('invalid_api_path')
        return path

    def _api(self,identifier,method,path,*,body=None,file=None,mime='application/json'):
        path=self._path(path)
        if method not in ('GET','POST'):raise ValueError('invalid_method')
        if path.split('?')[0]=='/v1/files/download':raise ValueError('use_chunked_download')
        headers={'Authorization':'Bearer '+self.token,'X-Request-ID':identifier,'Content-Type':mime}
        payload=file if file is not None else body
        if file is not None and os.fstat(file.fileno()).st_size==0:
            # requests would otherwise choose chunked transfer for an empty
            # stream, while the local API requires an explicit Content-Length.
            payload=b''
        with self.local.request(method,'http://127.0.0.1:'+str(self.server.port)+path,headers=headers,
                                data=payload,timeout=(5,40),stream=True,allow_redirects=False) as response:
            content=bytearray()
            for chunk in response.iter_content(65536):
                content.extend(chunk)
                if len(content)>2*1024*1024:raise ValueError('desktop_response_too_large')
            return {'status':response.status_code,'body':b64(bytes(content))}

    def _dispatch(self,identifier,value):
        op=value.get('op');args=value.get('args')
        if not isinstance(args,dict):raise ValueError('invalid_arguments')
        if op=='http':
            body=unb64(args.get('body',''))
            if len(body)>32768:raise ValueError('use_chunked_upload')
            return self._api(identifier,args.get('method'),args.get('path'),body=body or None)
        self._cleanup()
        if op=='upload_start':
            if len(self.transfers)>=4:raise ValueError('too_many_file_transfers')
            path=self._path(args.get('path'));mime=args.get('mime');size=args.get('size')
            audio=path.startswith('/v1/dictation?')
            cap=2*1024*1024 if audio else 20*1024*1024 if path=='/v1/uploads' else MAX_TRANSFER
            if (isinstance(size,bool) or not isinstance(size,int) or not 0<=size<=cap or
                not ((audio and mime=='audio/mp4') or (path=='/v1/uploads' and mime=='application/zip') or (path.startswith('/v1/files/upload?') and mime=='application/octet-stream'))):raise ValueError('invalid_file_transfer')
            if path.startswith('/v1/files/upload?'):
                self.server.handler.check_desktop()
                query=parse_qs(urlsplit(path).query,keep_blank_values=True)
                if set(query)!={'folder','name'} or any(len(v)!=1 for v in query.values()):raise ValueError('invalid_file_target')
                directory=self.server.handler.files.resolve(query['folder'][0])
                name=self.server.handler.files.name(query['name'][0])
                if not directory.is_dir() or (directory/name).exists():raise ValueError('destination_exists_or_invalid_folder')
            handle=tempfile.NamedTemporaryFile(dir=self.root,prefix='relay-upload-',delete=False)
            transfer=secrets.token_urlsafe(18)
            self.transfers[transfer]={'kind':'upload','file':handle,'path':Path(handle.name),'api_path':path,'mime':mime,'size':size,'offset':0,'last':time.monotonic(),'hash':hashlib.sha256()}
            return {'transfer':transfer,'chunk_size':CHUNK}
        if op=='download_start':
            self.server.handler.check_desktop()
            if len(self.transfers)>=4:raise ValueError('too_many_file_transfers')
            path=self.server.handler.files.resolve(args.get('path',''),file=True)
            handle=path.open('rb');size=os.fstat(handle.fileno()).st_size
            if size>MAX_TRANSFER:handle.close();raise ValueError('file_exceeds_256_MiB')
            transfer=secrets.token_urlsafe(18)
            self.transfers[transfer]={'kind':'download','file':handle,'size':size,'offset':0,'last':time.monotonic(),'hash':hashlib.sha256()}
            return {'transfer':transfer,'size':size,'chunk_size':CHUNK}
        transfer=args.get('transfer');item=self.transfers.get(transfer)
        if not item:raise ValueError('transfer_expired')
        item['last']=time.monotonic()
        if op=='transfer_cancel':self._discard(transfer);return {'cancelled':True}
        if op=='upload_chunk' and item['kind']=='upload':
            block=unb64(args.get('data',''))
            if args.get('offset')!=item['offset'] or not 0<len(block)<=CHUNK or item['offset']+len(block)>item['size']:raise ValueError('invalid_file_chunk')
            item['file'].write(block);item['hash'].update(block);item['offset']+=len(block)
            return {'offset':item['offset']}
        if op=='upload_finish' and item['kind']=='upload':
            if item['offset']!=item['size'] or args.get('sha256')!=item['hash'].hexdigest():self._discard(transfer);raise ValueError('file_integrity_check_failed')
            item['file'].close()
            try:
                with item['path'].open('rb') as source:
                    return self._api(identifier,'POST',item['api_path'],file=source,mime=item['mime'])
            finally:self._discard(transfer)
        if op=='download_chunk' and item['kind']=='download':
            self.server.handler.check_desktop()
            if args.get('offset')!=item['offset']:raise ValueError('invalid_file_offset')
            block=item['file'].read(min(CHUNK,item['size']-item['offset']))
            if not block and item['offset']<item['size']:self._discard(transfer);raise ValueError('file_changed_during_download')
            offset=item['offset'];item['offset']+=len(block);item['hash'].update(block)
            done=item['offset']==item['size'];result={'offset':offset,'data':b64(block),'done':done}
            if done:result['sha256']=item['hash'].hexdigest();self._discard(transfer)
            return result
        raise ValueError('invalid_transfer_operation')

    def _discard(self,transfer):
        item=self.transfers.pop(transfer,None)
        if item:
            item['file'].close()
            if item['kind']=='upload':item['path'].unlink(missing_ok=True)
    def _cleanup(self,all_transfers=False):
        for transfer,item in list(self.transfers.items()):
            if all_transfers or time.monotonic()-item['last']>300:self._discard(transfer)
    def stop(self):
        self.stop_event.set();self.connected=False;self._state='stopped'


class RelayWorker:
    def __init__(self,server,url,enrollment,token,root):
        self.server=server;self.args=(url,enrollment,token,server,root);self.bridge=None
    def start(self):
        if self.bridge and self.bridge.thread and self.bridge.thread.is_alive():return
        self.server.start()
        try:self.bridge=RelayBridge(*self.args);self.bridge.start()
        except Exception:self.server.stop();raise
    def stop(self):
        if self.bridge:self.bridge.stop()
        self.server.stop()
    def status_text(self):return self.bridge.status_text() if self.bridge else 'الاتصال التلقائي متوقف'
