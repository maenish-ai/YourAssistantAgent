"""Versioned end-to-end relay envelopes shared with the Android client.

The relay gets role credentials derived separately from the pairing secret. It
never receives the secret or the AES key. Random 96-bit nonces, 128-bit GCM tags,
and direction/channel/request-bound AAD prevent substitution between messages.
"""
from __future__ import annotations
import base64
import hashlib
import json
import os
import re
from urllib.parse import urlsplit
from cryptography.hazmat.primitives.ciphers.aead import AESGCM

MAX_ENVELOPE = 4 * 1024 * 1024


def b64(data): return base64.urlsafe_b64encode(data).decode('ascii').rstrip('=')
def unb64(value): return base64.urlsafe_b64decode(value + '=' * (-len(value) % 4))


def origin(value, *, local_test=False):
    value=str(value).strip().rstrip('/')
    parsed=urlsplit(value)
    if (parsed.scheme!='https' and not(local_test and parsed.scheme=='http' and parsed.hostname=='127.0.0.1')) or not parsed.hostname or parsed.username or parsed.password or parsed.path or parsed.query or parsed.fragment:
        raise ValueError('استخدم عنوان HTTPS للخادم بدون مسار أو بيانات دخول.')
    if parsed.port is not None and not 1<=parsed.port<=65535:raise ValueError('Invalid relay port')
    return parsed.geturl()


class RelayKeys:
    def __init__(self, token):
        if not isinstance(token,str) or not re.fullmatch(r'[A-Za-z0-9_-]{32,128}',token):raise ValueError('Invalid pairing secret')
        def derive(label):return hashlib.sha256(('yaa-relay-v1:'+label+'\0'+token).encode('utf-8')).digest()
        self.key=derive('encryption')
        self.channel=derive('channel').hex()[:32]
        self.desktop_auth=b64(derive('desktop'))
        self.phone_auth=b64(derive('phone'))

    def aad(self,direction,identifier):
        if direction not in {'request','response'} or not isinstance(identifier,str) or not re.fullmatch(r'[A-Za-z0-9_-]{8,80}',identifier):raise ValueError('Invalid envelope')
        return ('yaa-relay-v1|'+direction+'|'+self.channel+'|'+identifier).encode()

    def seal(self,direction,identifier,value):
        raw=json.dumps(value,ensure_ascii=False,separators=(',',':')).encode('utf-8')
        if len(raw)>2_900_000:raise ValueError('Relay message too large')
        nonce=os.urandom(12)
        ciphertext=AESGCM(self.key).encrypt(nonce,raw,self.aad(direction,identifier))
        return {'v':1,'id':identifier,'nonce':b64(nonce),'ciphertext':b64(ciphertext)}

    def open(self,direction,envelope):
        if not isinstance(envelope,dict) or set(envelope)!={'v','id','nonce','ciphertext'} or envelope['v']!=1:raise ValueError('Invalid envelope')
        if len(envelope['ciphertext'])>MAX_ENVELOPE:raise ValueError('Envelope too large')
        nonce=unb64(envelope['nonce'])
        if len(nonce)!=12:raise ValueError('Invalid nonce')
        raw=AESGCM(self.key).decrypt(nonce,unb64(envelope['ciphertext']),self.aad(direction,envelope['id']))
        value=json.loads(raw)
        if not isinstance(value,dict):raise ValueError('Invalid request')
        return value
