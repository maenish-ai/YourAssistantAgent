"""Personal HTTPS endpoint hosted by the unlocked desktop itself."""
from __future__ import annotations
import datetime as dt
import ipaddress
import json
import os
from pathlib import Path
import socket
import ssl
import tempfile
from urllib.parse import urlsplit
from cryptography import x509
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import ec
from cryptography.x509.oid import NameOID
from .settings import validate_remote_token

KEY_FILE='home-tls-key.enc'
CERT_FILE='home-tls-cert.pem'
KEY_AAD=b'yaa-home-tls-private-key-v1'


def endpoint(value):
    if not isinstance(value,str):raise ValueError('Invalid computer address')
    parsed=urlsplit(value.strip().rstrip('/'))
    if (parsed.scheme!='https' or not parsed.hostname or parsed.username is not None or parsed.password is not None or
            parsed.path or parsed.query or parsed.fragment or
            (parsed.port is not None and not 1<=parsed.port<=65535)):
        raise ValueError('استخدم عنوان HTTPS للكمبيوتر بدون مسار أو كلمة مرور.')
    return parsed.geturl()


def connection_scope(settings):
    """Describe configured reachability without claiming a remote probe passed."""
    mode = getattr(settings, 'remote_connection_mode', 'direct')
    if mode == 'relay':
        return 'وضع الوسيط مضبوط؛ هذه الحالة لا تختبر وصول الهاتف من شبكة أخرى.'
    if mode != 'home':
        return 'الاستضافة المنزلية HTTPS غير مفعلة؛ الاقتران المحلي لا يثبت الوصول من شبكة أخرى.'
    public = getattr(settings, 'remote_home_public_url', '')
    if not public:
        return 'لم يُضبط عنوان خارجي. الاتصال الحالي محلي؛ يلزم عنوان عام وتوجيه منفذ أو IPv6 قابل للوصول.'
    try:
        host = urlsplit(endpoint(public)).hostname
        try:
            address = ipaddress.ip_address(host)
        except ValueError:
            if host.lower() == 'localhost' or host.lower().endswith(('.local', '.localhost')):
                return 'العنوان الخارجي المضبوط محلي فقط؛ لن يعمل من شبكة أخرى.'
        else:
            if not address.is_global:
                return 'العنوان الخارجي المضبوط ليس عنواناً عاماً؛ لن يتيح الوصول عبر الإنترنت مباشرة.'
    except (TypeError, ValueError):
        return 'العنوان الخارجي غير صالح. راجع إعداد الاستضافة المنزلية.'
    return 'عنوان HTTPS خارجي مضبوط، لكن الوصول غير مُختبر. جرّب الاتصال ببيانات الهاتف؛ يلزم مسار من الراوتر إلى الكمبيوتر، وCGNAT قد يمنعه.'


def bind_address():
    if socket.has_ipv6:
        try:
            with socket.socket(socket.AF_INET6,socket.SOCK_STREAM) as probe:
                probe.setsockopt(socket.IPPROTO_IPV6,socket.IPV6_V6ONLY,0)
                probe.bind(('::',0))
            return '::'
        except OSError:pass
    return '0.0.0.0'


def local_address():
    # UDP connect selects the default interface; it sends no network packet.
    try:
        with socket.socket(socket.AF_INET,socket.SOCK_DGRAM) as probe:
            probe.connect(('192.0.2.1',9));address=probe.getsockname()[0]
            if not ipaddress.ip_address(address).is_loopback:return address
    except OSError:pass
    for result in socket.getaddrinfo(socket.gethostname(),None,socket.AF_INET):
        address=result[4][0]
        if not ipaddress.ip_address(address).is_loopback:return address
    raise ValueError('اتصل بشبكة البيت أولاً ليظهر عنوان الكمبيوتر.')


def identity(security):
    if not security.unlocked:raise ValueError('افتح قفل البرنامج أولاً.')
    root=Path(security.root);cert_path=root/CERT_FILE;key_path=root/KEY_FILE
    if not cert_path.exists() and not key_path.exists():
        key=ec.generate_private_key(ec.SECP256R1())
        name=x509.Name([x509.NameAttribute(NameOID.COMMON_NAME,'Your Assistant Personal Computer')])
        now=dt.datetime.now(dt.timezone.utc)
        cert=(x509.CertificateBuilder().subject_name(name).issuer_name(name).public_key(key.public_key())
              .serial_number(x509.random_serial_number()).not_valid_before(now-dt.timedelta(days=1))
              .not_valid_after(now+dt.timedelta(days=3650))
              .add_extension(x509.BasicConstraints(ca=False,path_length=None),critical=True)
              .add_extension(x509.SubjectAlternativeName([x509.DNSName('localhost'),x509.IPAddress(ipaddress.ip_address('127.0.0.1'))]),critical=False)
              .sign(key,hashes.SHA256()))
        pem=key.private_bytes(serialization.Encoding.PEM,serialization.PrivateFormat.PKCS8,serialization.NoEncryption())
        encrypted=security.encrypt(pem,aad=KEY_AAD)
        # Exclusive creation preserves identity across restarts and upgrades.
        with key_path.open('xb') as target:target.write(encrypted)
        try:key_path.chmod(0o600)
        except OSError:pass
        with cert_path.open('xb') as target:target.write(cert.public_bytes(serialization.Encoding.PEM))
    if not cert_path.exists() or not key_path.exists():raise ValueError('ملفات هوية الكمبيوتر غير مكتملة. استعد نسختها الاحتياطية.')
    cert=x509.load_pem_x509_certificate(cert_path.read_bytes())
    now=dt.datetime.now(dt.timezone.utc)
    if not cert.not_valid_before_utc<=now<=cert.not_valid_after_utc:raise ValueError('شهادة الكمبيوتر منتهية أو ساعة الجهاز غير صحيحة.')
    pem=security.decrypt(key_path.read_bytes(),aad=KEY_AAD)
    key=serialization.load_pem_private_key(pem,password=None)
    public=lambda value:value.public_bytes(serialization.Encoding.DER,serialization.PublicFormat.SubjectPublicKeyInfo)
    if public(key.public_key())!=public(cert.public_key()):raise ValueError('هوية الكمبيوتر لا تطابق مفتاحها.')
    return cert,pem


def tls_context(security):
    cert,pem=identity(security)
    context=ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER);context.minimum_version=ssl.TLSVersion.TLSv1_2
    context.set_alpn_protocols(['http/1.1'])
    # load_cert_chain requires filenames. Private PEM exists only briefly,
    # owner-only, and is unlinked immediately after OpenSSL loads it.
    fd,name=tempfile.mkstemp(prefix='yaa-tls-',suffix='.pem')
    try:
        with os.fdopen(fd,'wb') as output:output.write(pem)
        context.load_cert_chain(str(Path(security.root)/CERT_FILE),name)
    finally:Path(name).unlink(missing_ok=True)
    return context,cert.fingerprint(hashes.SHA256()).hex()


def pairing_payload(security,token,port,public_url='',lan_url=''):
    cert,_=identity(security)
    if isinstance(port,bool) or not 1024<=int(port)<=65535:raise ValueError('اختر منفذاً بين 1024 و65535.')
    urls=[]
    if lan_url:urls.append(endpoint(lan_url))
    else:
        try:urls.append(endpoint('https://'+local_address()+':'+str(port)))
        except (ValueError,OSError):
            if not public_url:raise
    if public_url:
        public=endpoint(public_url)
        if public not in urls:urls.append(public)
    return json.dumps({'type':'yaa-direct','v':1,'urls':urls,'cert_sha256':cert.fingerprint(hashes.SHA256()).hex(),
                       'token':validate_remote_token(token)},separators=(',',':'))


class HomeWorker:
    def __init__(self,server):self.server=server
    def start(self):return self.server.start()
    def stop(self):return self.server.stop()
    def status_text(self):
        if not self.server._accepting.is_set():return 'خادم الكمبيوتر متوقف'
        import time
        if self.server._last_seen and time.time()-self.server._last_seen<15:return 'الهاتف متصل مباشرة بالكمبيوتر — HTTPS'
        return 'خادم الكمبيوتر يعمل على المنفذ '+str(self.server.port)+' — امسح QR داخل شبكة البيت أولاً'
