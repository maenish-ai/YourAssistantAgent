"""Authenticated Android API with loopback and explicit personal HTTPS modes.

Legacy mode stays on loopback for an owner's reverse proxy. Personal hosting
binds the home interfaces only with a TLS context. Application tasks are queued
rather than executed by HTTP request threads.
"""
from __future__ import annotations

from collections import deque
import hashlib
import hmac
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import json
from pathlib import Path
import queue
import re
import secrets
import socket
import ssl
import sys
import threading
import time
from urllib.parse import parse_qs, urlsplit
import zipfile

MAX_UPLOAD_BYTES = 20 * 1024 * 1024
MAX_JSON_BYTES = 32 * 1024
MAX_EVENTS_RESPONSE_BYTES = 1024 * 1024
_REQUEST_ID = re.compile(r'^[A-Za-z0-9_-]{8,128}$')
_NONCE = re.compile(r'^[A-Za-z0-9_-]{8,100}$')
_TOKEN = re.compile(r'^[A-Za-z0-9_-]{32,128}$')


class MobileServerError(RuntimeError):
    pass


class MobileServer:
    def __init__(self, token: str, handler, inbox: Path, port: int = 8766, activity=None, keep_awake=False, bind='127.0.0.1', tls_context=None):
        if not isinstance(token, str) or not _TOKEN.fullmatch(token):
            raise MobileServerError('Invalid Android pairing token')
        if not 0 <= int(port) <= 65535:
            raise MobileServerError('Invalid Android companion port')
        self._token = token
        self.handler = handler
        self.inbox = Path(inbox)
        self.port = int(port)
        if bind not in ('127.0.0.1','0.0.0.0','::') or (bind!='127.0.0.1' and tls_context is None):
            raise MobileServerError('Non-loopback connections require HTTPS')
        self.bind,self.tls_context=bind,tls_context
        self.activity = activity or (lambda *_: None)
        from .power import AwakeGuard
        self._power = AwakeGuard(keep_awake, activity=self.activity)
        self._lock = threading.RLock()
        self._events = deque(maxlen=512)
        self._event_id = 0
        self._requests = {}
        self._jobs = queue.Queue(maxsize=16)
        self._stopping = threading.Event()
        self._accepting = threading.Event()
        self._server = None
        self._http_thread = None
        self._worker = None
        self._last_seen = 0.0

    def publish(self, text: str, approval_token: str | None = None, expires_at: float | None = None,
                clear_approval: bool = False, download_path=None, download_name=None) -> dict:
        if len(str(text)) > 65536:
            raise MobileServerError('Android message exceeds event limit')
        if approval_token is not None and not _NONCE.fullmatch(approval_token):
            raise MobileServerError('Invalid approval identifier')
        with self._lock:
            if self._stopping.is_set():
                return {}
            self._event_id += 1
            event = {'id': self._event_id, 'type': 'approval' if approval_token else 'message',
                     'text': str(text), 'created_at': time.time()}
            if clear_approval:
                event['clear_approval'] = True
            if download_path is not None:
                event.update(type='file', download_path=str(download_path), download_name=str(download_name or 'download'))
            if approval_token:
                event.update(token=approval_token, expires_at=float(expires_at or time.time() + 900))
            self._events.append(event)
            return dict(event)

    def send_message(self, chat_id, text: str, reply_markup=None) -> dict:
        """Channel adapter used by the desktop assistant service."""
        approval_token = None
        if isinstance(reply_markup, dict):
            for row in reply_markup.get('inline_keyboard', []):
                for button in row:
                    data = str(button.get('callback_data') or '')
                    if data.startswith('approve:'):
                        approval_token = data.split(':', 1)[1]
        expiry = reply_markup.get('expires_at') if isinstance(reply_markup, dict) else None
        event = self.publish(text, approval_token=approval_token, expires_at=expiry)
        return {'message_id': event.get('id', 0), **event}

    def status_text(self) -> str:
        if not self._accepting.is_set():
            return 'Android connection stopped'
        if self._last_seen and time.time() - self._last_seen < 15:
            return f'Android connected — 127.0.0.1:{self.port}'
        return f'Android waiting for phone — 127.0.0.1:{self.port}'

    def _snapshot(self, after: int) -> dict:
        with self._lock:
            oldest = self._events[0]['id'] if self._events else self._event_id + 1
            reset = after > self._event_id or after < oldest - 1
            selected = []
            # The native app bounds responses to 2 MiB. Account for UTF-8
            # bytes, not character count: full Arabic previews can be large.
            # Leave room for envelope fields and delimiters.
            encoded_size = 1024
            for event in self._events:
                if not reset and event['id'] <= after:
                    continue
                event_size = len(json.dumps(event, ensure_ascii=False).encode('utf-8')) + 2
                if selected and (len(selected) >= 100 or encoded_size + event_size > MAX_EVENTS_RESPONSE_BYTES):
                    break
                selected.append(dict(event))
                encoded_size += event_size
            cursor = selected[-1]['id'] if selected else self._event_id
            return {'events': selected, 'cursor': cursor, 'reset': reset}

    def _enqueue(self, request_id: str, fingerprint: str, task: tuple) -> tuple[int, dict]:
        with self._lock:
            if not self._accepting.is_set():
                return 503, {'error': 'connection_stopping'}
            previous = self._requests.get(request_id)
            if previous:
                old_fingerprint, job_id = previous
                if not hmac.compare_digest(old_fingerprint, fingerprint):
                    return 409, {'error': 'request_id_conflict'}
                return 202, {'job_id': job_id, 'duplicate': True}
            if len(self._requests) >= 4096:
                return 429, {'error': 'request_limit_restart_connection'}
            job_id = secrets.token_urlsafe(12)
            try:
                self._jobs.put_nowait((job_id, task))
            except queue.Full:
                return 429, {'error': 'task_queue_full'}
            self._requests[request_id] = (fingerprint, job_id)
            return 202, {'job_id': job_id}

    def _run_jobs(self):
        while not self._stopping.is_set():
            try:
                job_id, task = self._jobs.get(timeout=.2)
            except queue.Empty:
                continue
            try:
                if self._stopping.is_set():
                    if task[0] == 'document':
                        task[1].unlink(missing_ok=True)
                    elif task[0] == 'file_import':
                        task[1][0].unlink(missing_ok=True)
                    continue
                kind, value = task
                if kind == 'text':
                    self.handler.text(value)
                elif kind == 'document':
                    self.handler.document(value, '')
                elif kind == 'desktop_input':
                    self.handler.desktop_input(value)
                elif kind == 'file_import':
                    self.handler.file_import(*value)
                else:
                    self.handler.callback(value)
            except Exception:
                # Exceptions from HTTP libraries can contain credentials/URLs.
                # Never forward their text to the phone or activity log.
                self.publish('تعذر إكمال المهمة. افحص حالة البرنامج على الكمبيوتر قبل إعادة المحاولة.')
                self.activity('remote_task_error', f'job={job_id}; operation failed')
                if task[0] == 'document':
                    task[1].unlink(missing_ok=True)
                elif task[0] == 'file_import':
                    task[1][0].unlink(missing_ok=True)
            finally:
                self._jobs.task_done()

    def start(self) -> bool:
        if self._accepting.is_set():
            return True
        if self._stopping.is_set():
            raise MobileServerError('Create a new Android connection after stopping it')
        self.inbox.mkdir(parents=True, exist_ok=True)
        companion = self

        class Handler(BaseHTTPRequestHandler):
            protocol_version = 'HTTP/1.1'
            server_version = 'YourAssistant'
            sys_version = ''

            def setup(self):
                super().setup()
                self.connection.settimeout(15)

            def log_message(self, *_):
                pass

            def _send(self, status: int, payload: dict):
                body = json.dumps(payload, ensure_ascii=False).encode('utf-8')
                self.send_response(status)
                self.send_header('Content-Type', 'application/json; charset=utf-8')
                self.send_header('Content-Length', str(len(body)))
                self.send_header('Cache-Control', 'no-store')
                self.send_header('X-Content-Type-Options', 'nosniff')
                self.send_header('Connection', 'close')
                self.end_headers()
                self.close_connection = True
                try:
                    self.wfile.write(body)
                except (BrokenPipeError, ConnectionResetError):
                    pass

            def _authorized(self) -> bool:
                # The native Android client sends no Origin. Disallow webpages
                # from using this loopback bridge, even if they know its URL.
                if self.headers.get('Origin') is not None:
                    self._send(403, {'error': 'browser_origin_not_allowed'})
                    return False
                authorization = self.headers.get('Authorization', '')
                expected = 'Bearer ' + companion._token
                if not hmac.compare_digest(authorization.encode('utf-8'), expected.encode('ascii')):
                    self._send(401, {'error': 'unauthorized'})
                    return False
                if not companion._accepting.is_set():
                    self._send(503, {'error': 'connection_stopping'})
                    return False
                companion._last_seen = time.time()
                return True

            def do_OPTIONS(self):
                self._send(405, {'error': 'method_not_allowed'})

            def do_GET(self):
                if not self._authorized():
                    return
                parsed = urlsplit(self.path)
                if parsed.path == '/v1/capabilities':
                    return self._send(200, companion.handler.capabilities())
                if parsed.path in {'/v1/desktop', '/v1/files', '/v1/files/download'}:
                    transfer_started = False
                    try:
                        companion.handler.check_desktop()
                        if parsed.path == '/v1/desktop':
                            return self._send(200, companion.handler.desktop.frame())
                        query = parse_qs(parsed.query)
                        relative = query.get('path', [''])[0]
                        if parsed.path == '/v1/files':
                            return self._send(200, companion.handler.files.listing(relative))
                        from .files import MAX_TRANSFER
                        path = companion.handler.files.resolve(relative, file=True)
                        # Open first, then size the actual descriptor we stream.
                        with path.open('rb') as source:
                            import os
                            size = os.fstat(source.fileno()).st_size
                            if size > MAX_TRANSFER:
                                return self._send(413, {'error': 'File exceeds 256 MiB'})
                            transfer_started = True
                            self.send_response(200)
                            self.send_header('Content-Type', 'application/octet-stream')
                            self.send_header('Content-Length', str(size))
                            self.send_header('Cache-Control', 'no-store')
                            self.send_header('Connection', 'close')
                            self.end_headers()
                            self.close_connection = True
                            remaining = size
                            while remaining:
                                chunk = source.read(min(65536, remaining))
                                if not chunk:break
                                self.wfile.write(chunk)
                                remaining -= len(chunk)
                        return
                    except (BrokenPipeError, ConnectionResetError):
                        return
                    except Exception as exc:
                        if transfer_started:
                            self.close_connection = True
                            return
                        from .desktop import DesktopError
                        from .files import FileError
                        return self._send(400, {'error': str(exc) if isinstance(exc,(DesktopError,FileError)) else 'Desktop/file operation unavailable'})
                if parsed.path != '/v1/events':
                    return self._send(404, {'error': 'not_found'})
                try:
                    query = parse_qs(parsed.query, strict_parsing=bool(parsed.query))
                    if set(query) - {'after'}:
                        raise ValueError()
                    values = query.get('after', ['0'])
                    if len(values) != 1 or not values[0].isdigit():
                        raise ValueError()
                    after = int(values[0])
                except ValueError:
                    return self._send(400, {'error': 'invalid_cursor'})
                self._send(200, companion._snapshot(after))

            def _length(self, maximum: int, allow_empty=False) -> int | None:
                lengths = self.headers.get_all('Content-Length') or []
                if self.headers.get('Transfer-Encoding') is not None or len(lengths) != 1 or not re.fullmatch(r'[0-9]{1,10}', lengths[0]):
                    self._send(400, {'error': 'content_length_required'})
                    return None
                length = int(lengths[0])
                if length > maximum:
                    self._send(413, {'error': 'payload_too_large'})
                    return None
                if length == 0 and not allow_empty:
                    self._send(400, {'error': 'empty_payload'})
                    return None
                return length

            def do_POST(self):
                if not self._authorized():
                    return
                parsed = urlsplit(self.path)
                path = parsed.path
                if path not in {'/v1/messages', '/v1/new-chat', '/v1/uploads', '/v1/approvals', '/v1/desktop/input', '/v1/desktop/stop', '/v1/files/upload'}:
                    return self._send(404, {'error': 'not_found'})
                request_id = self.headers.get('X-Request-ID', '')
                if not _REQUEST_ID.fullmatch(request_id):
                    return self._send(400, {'error': 'request_id_required'})
                content_type = self.headers.get('Content-Type', '').split(';', 1)[0].strip().lower()
                is_upload = path == '/v1/uploads'
                is_file = path == '/v1/files/upload'
                if content_type != ('application/octet-stream' if is_file else 'application/zip' if is_upload else 'application/json'):
                    return self._send(415, {'error': 'unsupported_media_type'})
                from .files import MAX_TRANSFER
                length = self._length(MAX_TRANSFER if is_file else MAX_UPLOAD_BYTES if is_upload else MAX_JSON_BYTES, allow_empty=is_file)
                if length is None:
                    return
                uploaded = None
                try:
                    digest = hashlib.sha256(self.path.encode('utf-8'))
                    if is_upload or is_file:
                        if is_file:
                            companion.handler.check_desktop()
                            query = parse_qs(parsed.query, keep_blank_values=True)
                            if set(query) != {'folder','name'} or any(len(v)!=1 for v in query.values()):raise ValueError()
                            folder, name = query['folder'][0], query['name'][0]
                            companion.handler.files.resolve(folder)
                            companion.handler.files.name(name)
                        uploaded = companion.inbox / (secrets.token_hex(16) + ('.bin' if is_file else '.zip'))
                        remaining = length
                        with uploaded.open('xb') as output:
                            while remaining:
                                block = self.rfile.read(min(65536, remaining))
                                if not block:
                                    raise ValueError()
                                output.write(block)
                                digest.update(block)
                                remaining -= len(block)
                        if is_upload and not zipfile.is_zipfile(uploaded):
                            raise ValueError()
                        task = ('file_import', (uploaded, folder, name)) if is_file else ('document', uploaded)
                    else:
                        raw = self.rfile.read(length)
                        if len(raw) != length:
                            raise ValueError()
                        digest.update(raw)
                        data = json.loads(raw.decode('utf-8'))
                        if not isinstance(data, dict):
                            raise ValueError()
                        if path == '/v1/messages':
                            value = data.get('text')
                            if set(data) != {'text'} or not isinstance(value, str) or not value.strip() or len(value) > 6000:
                                raise ValueError()
                            task = ('text', value.strip())
                        elif path == '/v1/desktop/input':
                            companion.handler.check_desktop()
                            task = ('desktop_input', data)
                        elif path == '/v1/desktop/stop':
                            if data:raise ValueError()
                            companion.handler.stop_desktop_task()
                            return self._send(202, {'job_id': 'stop-requested'})
                        elif path == '/v1/new-chat':
                            if data:
                                raise ValueError()
                            task = ('text', '/new')
                        else:
                            nonce = data.get('token')
                            approved = data.get('approve')
                            if set(data) != {'token', 'approve'} or not isinstance(nonce, str) or not _NONCE.fullmatch(nonce) or type(approved) is not bool:
                                raise ValueError()
                            task = ('callback', ('approve:' if approved else 'cancel:') + nonce)
                    status, payload = companion._enqueue(request_id, digest.hexdigest(), task)
                    if uploaded and (status != 202 or payload.get('duplicate')):
                        uploaded.unlink(missing_ok=True)
                    self._send(status, payload)
                except Exception:
                    if uploaded:
                        uploaded.unlink(missing_ok=True)
                    self._send(400, {'error': 'invalid_payload'})

        class Server(ThreadingHTTPServer):
            daemon_threads = True
            address_family=socket.AF_INET6 if ':' in companion.bind else socket.AF_INET
            def server_bind(self):
                if self.address_family==socket.AF_INET6:
                    self.socket.setsockopt(socket.IPPROTO_IPV6,socket.IPV6_V6ONLY,0)
                super().server_bind()
            def handle_error(self,request,address):
                if not isinstance(sys.exc_info()[1],(ConnectionError,ssl.SSLError,TimeoutError)):
                    companion.activity("remote_transport_error",type(sys.exc_info()[1]).__name__)
            def process_request(self,request,address):
                if not self.slots.acquire(blocking=False):request.close();return
                try:super().process_request(request,address)
                except Exception:self.slots.release();raise
            def process_request_thread(self,request,address):
                try:super().process_request_thread(request,address)
                finally:self.slots.release()

        try:
            self._server = Server((self.bind, self.port), Handler)
            self._server.slots=threading.BoundedSemaphore(32)
            if self.tls_context:
                self._server.socket=self.tls_context.wrap_socket(self._server.socket,server_side=True,do_handshake_on_connect=False)
        except OSError as exc:
            raise MobileServerError('Android companion port is unavailable') from exc
        self.port = self._server.server_address[1]
        self._accepting.set()
        self._worker = threading.Thread(target=self._run_jobs, daemon=True, name='yaa-android-tasks')
        self._http_thread = threading.Thread(target=self._server.serve_forever, daemon=True, name='yaa-android-api')
        self._worker.start()
        self._http_thread.start()
        self._power.start()
        self.activity('remote_started', f'Android companion port:{self.port}, TLS:{self.tls_context is not None}')
        return True

    def stop(self) -> None:
        self._power.stop()
        self._accepting.clear()
        self._stopping.set()
        if hasattr(self.handler, 'close'):
            try:
                self.handler.close()
            except Exception:
                self.activity('remote_close_error', 'Android handler cleanup failed')
        while True:
            try:
                _, task = self._jobs.get_nowait()
            except queue.Empty:
                break
            if task[0] == 'document':
                task[1].unlink(missing_ok=True)
            elif task[0] == 'file_import':
                task[1][0].unlink(missing_ok=True)
            self._jobs.task_done()
        if self._server:
            self._server.shutdown()
            self._server.server_close()
            self._server = None
        if self._worker and self._worker is not threading.current_thread():
            self._worker.join(timeout=.5)
