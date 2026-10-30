"""Encrypted, local pairing credentials for the optional Android connection."""
from __future__ import annotations

import os
from pathlib import Path
import re
import secrets

from ..security.manager import SecurityError, SecurityManager

TOKEN_FILE = 'remote-token.enc'
TOKEN_AAD = b'yaa-mobile-pairing'
_TOKEN = re.compile(r'^[A-Za-z0-9_-]{32,128}$')


def validate_remote_token(token: str) -> str:
    value = str(token or '').strip()
    if not _TOKEN.fullmatch(value):
        raise ValueError('Invalid pairing token. Generate a new token in Android & GitHub settings.')
    return value


def save_remote_token(security: SecurityManager, token: str) -> None:
    value = validate_remote_token(token)
    destination = Path(security.root) / TOKEN_FILE
    encrypted = security.encrypt(value.encode('utf-8'), aad=TOKEN_AAD)
    temporary = destination.with_suffix('.tmp')
    try:
        temporary.write_bytes(encrypted)
        try:
            os.chmod(temporary, 0o600)
        except OSError:
            pass
        temporary.replace(destination)
    finally:
        temporary.unlink(missing_ok=True)


def generate_remote_token(security: SecurityManager) -> str:
    value = secrets.token_urlsafe(32)
    save_remote_token(security, value)
    return value


def load_remote_token(security: SecurityManager) -> str:
    source = Path(security.root) / TOKEN_FILE
    if not source.exists():
        return ''
    try:
        value = security.decrypt(source.read_bytes(), aad=TOKEN_AAD).decode('utf-8')
        return validate_remote_token(value)
    except Exception as exc:
        raise SecurityError('Could not unlock the pairing token. Generate a new token in Android & GitHub settings.') from exc

RELAY_CREDENTIAL_FILE='relay-enrollment.enc'
RELAY_CREDENTIAL_AAD=b'yaa-relay-enrollment'


def save_relay_enrollment(security, value):
    value=str(value or '').strip()
    if not 32<=len(value)<=256 or '\n' in value or '\r' in value:raise ValueError('أدخل مفتاح تسجيل الخادم الصحيح.')
    path=Path(security.root)/RELAY_CREDENTIAL_FILE
    temporary=path.with_suffix('.tmp')
    temporary.write_bytes(security.encrypt(value.encode(),aad=RELAY_CREDENTIAL_AAD))
    try:os.chmod(temporary,0o600)
    except OSError:pass
    temporary.replace(path)


def load_relay_enrollment(security):
    path=Path(security.root)/RELAY_CREDENTIAL_FILE
    if not path.exists():return ''
    try:return security.decrypt(path.read_bytes(),aad=RELAY_CREDENTIAL_AAD).decode()
    except Exception as exc:raise SecurityError('تعذر فتح مفتاح خادم الربط المحفوظ.') from exc


def pairing_payload(url,token):
    import json
    from .relay_protocol import origin
    return json.dumps({'type':'yaa-relay','v':1,'url':origin(url),'token':validate_remote_token(token)},separators=(',',':'))
