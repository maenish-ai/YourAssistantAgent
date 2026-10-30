"""Bounded opaque mailbox relay. Deploy behind HTTPS; one process per instance.

No pairing secret, plaintext desktop request, file content or API token is
available to this server. Enrollment is private to the installation owner.
"""
from __future__ import annotations
from collections import deque
import hashlib
import hmac
from http.server import BaseHTTPRequestHandler,ThreadingHTTPServer
import json
import os
import re
import threading
import time

MAX_BODY=4*1024*1024
ID=re.compile(r'^[A-Za-z0-9_-]{8,80}$')
CHANNEL=re.compile(r'^[a-f0-9]{32}$')


def digest(value):return hashlib.sha256(value.encode()).hexdigest()


class Broker:
    def __init__(self,enrollment_key):
        if not isinstance(enrollment_key,str) or len(enrollment_key)<32:raise ValueError('Set RELAY_ENROLLMENT_KEY to at least 32 random characters')
        self.enrollment=digest(enrollment_key);self.lock=threading.RLock();self.channels={}

    def authenticate(self,channel,role,token):
        with self.lock:
            info=self.channels.get(channel)
            if not info or not hmac.compare_digest(info[role],digest(token)):return None
            return info

    def cleanup(self,info):
        now=time.monotonic()
        for identifier in list(info['jobs']):
            if now-info['jobs'][identifier]['created']>90:del info['jobs'][identifier]
        info['queue']=deque(i for i in info['queue'] if i in info['jobs'])

    def register(self,token,data):
        if not hmac.compare_digest(digest(token),self.enrollment):return 403,{'error':'enrollment_denied'}
        if set(data)!={'channel','desktop_auth','phone_auth'} or not CHANNEL.fullmatch(str(data['channel'])):return 400,{'error':'invalid_registration'}
        if any(not re.fullmatch(r'[A-Za-z0-9_-]{43}',str(data[k])) for k in ('desktop_auth','phone_auth')):return 400,{'error':'invalid_registration'}
        channel=data['channel'];desktop=digest(data['desktop_auth']);phone=digest(data['phone_auth'])
        with self.lock:
            existing=self.channels.get(channel)
            if existing and (existing['desktop']!=desktop or existing['phone']!=phone):return 409,{'error':'channel_conflict'}
            if not existing:
                for old in list(self.channels):
                    if time.monotonic()-self.channels[old]['seen']>3600:del self.channels[old]
                if len(self.channels)>=32:return 429,{'error':'channel_limit'}
                existing=self.channels[channel]={'desktop':desktop,'phone':phone,'seen':time.monotonic(),'queue':deque(),'jobs':{}}
            existing['seen']=time.monotonic()
        return 200,{'ok':True}

    @staticmethod
    def envelope(value):
        return (isinstance(value,dict) and set(value)=={'v','id','nonce','ciphertext'} and value['v']==1
                and isinstance(value['id'],str) and ID.fullmatch(value['id'])
                and isinstance(value['nonce'],str) and re.fullmatch(r'[A-Za-z0-9_-]{16}',value['nonce'])
                and isinstance(value['ciphertext'],str) and 22<=len(value['ciphertext'])<MAX_BODY
                and re.fullmatch(r'[A-Za-z0-9_-]+',value['ciphertext']))

    def request(self,info,value):
        if not self.envelope(value):return 400,{'error':'invalid_envelope'}
        with self.lock:
            self.cleanup(info)
            if time.monotonic()-info['seen']>45:return 503,{'error':'computer_offline'}
            identifier=value['id'];old=info['jobs'].get(identifier)
            if old:
                if old['request']!=value:return 409,{'error':'request_conflict'}
                if old['response'] is None and identifier not in info['queue'] and time.monotonic()-old.get('delivered',0)>2:info['queue'].append(identifier)
                return 202,{'id':identifier}
            if len(info['jobs'])>=32:return 429,{'error':'queue_full'}
            info['jobs'][identifier]={'request':value,'response':None,'created':time.monotonic(),'event':threading.Event()}
            info['queue'].append(identifier)
        return 202,{'id':identifier}


class RelayServer(ThreadingHTTPServer):
    daemon_threads=True
    def __init__(self,address,broker):
        self.broker=broker;self.stopping=threading.Event();self.slots=threading.BoundedSemaphore(64)
        super().__init__(address,Handler)
    def shutdown(self):
        self.stopping.set()
        with self.broker.lock:
            for channel in self.broker.channels.values():
                for job in channel['jobs'].values():job['event'].set()
        return super().shutdown()
    def process_request(self,request,address):
        if not self.slots.acquire(blocking=False):request.close();return
        try:super().process_request(request,address)
        except Exception:self.slots.release();raise
    def process_request_thread(self,request,address):
        try:super().process_request_thread(request,address)
        finally:self.slots.release()


class Handler(BaseHTTPRequestHandler):
    def setup(self):super().setup();self.connection.settimeout(25)
    def log_message(self,*args):pass
    def send(self,status,value):
        raw=json.dumps(value,separators=(',',':')).encode()
        self.send_response(status);self.send_header('Content-Type','application/json');self.send_header('Content-Length',str(len(raw)))
        self.send_header('Cache-Control','no-store');self.send_header('Connection','close');self.end_headers();self.close_connection=True
        try:self.wfile.write(raw)
        except (BrokenPipeError,ConnectionResetError):pass
    def body(self):
        sizes=self.headers.get_all('Content-Length') or []
        if self.headers.get('Transfer-Encoding') or len(sizes)!=1 or not re.fullmatch(r'[0-9]{1,8}',sizes[0]):raise ValueError()
        size=int(sizes[0])
        if not 0<size<=MAX_BODY:raise ValueError()
        data=self.rfile.read(size)
        if len(data)!=size:raise ValueError()
        value=json.loads(data)
        if not isinstance(value,dict):raise ValueError()
        return value
    def auth(self,role):
        parts=self.path.split('/')
        if self.headers.get('Origin') is not None or len(parts)<4 or parts[:3]!=['','relay','v1'] or not CHANNEL.fullmatch(parts[3]):return None
        header=self.headers.get('Authorization','')
        if not header.startswith('Bearer '):return None
        return self.server.broker.authenticate(parts[3],role,header[7:])
    def do_POST(self):
        broker=self.server.broker
        if self.headers.get('Origin') is not None:return self.send(403,{'error':'browser_not_allowed'})
        if self.path=='/relay/v1/register':
            header=self.headers.get('Authorization','')
            if not header.startswith('Bearer ') or not hmac.compare_digest(digest(header[7:]),broker.enrollment):return self.send(403,{'error':'enrollment_denied'})
            try:status,value=broker.register(header[7:],self.body())
            except Exception:return self.send(400,{'error':'invalid_registration'})
            return self.send(status,value)
        parts=self.path.split('/')
        if len(parts)==5 and parts[4]=='requests':
            info=self.auth('phone')
            if info is None:return self.send(403,{'error':'access_denied'})
            try:status,value=broker.request(info,self.body())
            except Exception:return self.send(400,{'error':'invalid_envelope'})
            return self.send(status,value)
        if len(parts)==6 and parts[4]=='response' and ID.fullmatch(parts[5]):
            info=self.auth('desktop')
            if info is None:return self.send(403,{'error':'access_denied'})
            try:value=self.body()
            except Exception:return self.send(400,{'error':'invalid_envelope'})
            if not broker.envelope(value) or value['id']!=parts[5]:return self.send(400,{'error':'invalid_envelope'})
            with broker.lock:
                job=info['jobs'].get(parts[5])
                if not job:return self.send(404,{'error':'request_expired'})
                if job['response'] is None:job['response']=value;job['event'].set()
            return self.send(200,{'ok':True})
        self.send(404,{'error':'not_found'})
    def do_GET(self):
        if self.path=='/health':return self.send(200,{'ok':True,'protocol':1})
        broker=self.server.broker;parts=self.path.split('/')
        if len(parts)==5 and parts[4]=='next':
            info=self.auth('desktop')
            if info is None:return self.send(403,{'error':'access_denied'})
            until=time.monotonic()+18
            while time.monotonic()<until and not self.server.stopping.is_set():
                with broker.lock:
                    info['seen']=time.monotonic();broker.cleanup(info)
                    if info['queue']:
                        identifier=info['queue'].popleft()
                        info['jobs'][identifier]['delivered']=time.monotonic()
                        return self.send(200,{'request':info['jobs'][identifier]['request']})
                time.sleep(.1)
            return self.send(200,{'request':None})
        if len(parts)==6 and parts[4]=='requests' and ID.fullmatch(parts[5]):
            info=self.auth('phone')
            if info is None:return self.send(403,{'error':'access_denied'})
            with broker.lock:job=info['jobs'].get(parts[5])
            if not job:return self.send(404,{'error':'request_expired'})
            job['event'].wait(18)
            with broker.lock:response=job['response']
            return self.send(200,response) if response else self.send(202,{'waiting':True})
        self.send(404,{'error':'not_found'})
    def do_DELETE(self):
        parts=self.path.split('/')
        if len(parts)==6 and parts[4]=='requests':
            info=self.auth('phone')
            if info is None:return self.send(403,{'error':'access_denied'})
            with self.server.broker.lock:info['jobs'].pop(parts[5],None)
            return self.send(200,{'ok':True})
        self.send(404,{'error':'not_found'})


def main():
    broker=Broker(os.environ.get('RELAY_ENROLLMENT_KEY',''))
    server=RelayServer((os.environ.get('RELAY_BIND','127.0.0.1'),int(os.environ.get('PORT','8080'))),broker)
    print("Encrypted relay ready",flush=True)
    server.serve_forever()

if __name__=='__main__':main()
