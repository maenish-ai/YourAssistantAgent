"""Exercise the real Android companion HTTP boundary without accounts/network."""
from io import BytesIO
import json
import queue
import threading
from urllib.error import HTTPError
from urllib.request import Request, urlopen
import zipfile

import pytest

from yaa_lite.remote.mobile import MAX_UPLOAD_BYTES, MobileServer, MobileServerError

TOKEN = 'A' * 43


class Assistant:
    def __init__(self):
        self.calls = queue.Queue()
        self.closed = False

    def text(self, text):
        self.calls.put(('text', text))

    def document(self, path, caption):
        self.calls.put(('document', path))

    def callback(self, callback):
        self.calls.put(('callback', callback))

    def close(self):
        self.closed = True


@pytest.fixture
def companion(tmp_path):
    handler = Assistant()
    server = MobileServer(TOKEN, handler, tmp_path / 'inbox', port=0)
    assert server.start()
    yield server, handler
    server.stop()


def request(server, path, data=None, *, headers=None, raw=None, token=TOKEN, request_id='request_1234'):
    head = {'Authorization': 'Bearer ' + token}
    if data is not None:
        raw = json.dumps(data, ensure_ascii=False).encode()
        head.update({'Content-Type': 'application/json', 'X-Request-ID': request_id})
    if headers:
        head.update(headers)
    req = Request(f'http://127.0.0.1:{server.port}' + path, data=raw, headers=head)
    try:
        response = urlopen(req, timeout=3)
    except HTTPError as error:
        response = error
    with response:
        return response.code, json.load(response), dict(response.headers)


def make_zip():
    stream = BytesIO()
    with zipfile.ZipFile(stream, 'w') as archive:
        archive.writestr('src/example.py', 'print("hello")')
    return stream.getvalue()


def test_bound_to_loopback_and_no_tasks_until_requested(companion):
    server, handler = companion
    assert server._server.server_address[0] == '127.0.0.1'
    assert handler.calls.empty()
    assert 'waiting' in server.status_text()
    status, body, _ = request(server, '/v1/events?after=0')
    assert status == 200 and body['events'] == []
    assert 'connected' in server.status_text()


def test_auth_and_origin_are_required_for_every_endpoint(companion):
    server, handler = companion
    for path, data in [('/v1/events', None), ('/v1/messages', {'text': 'publish'})]:
        status, body, headers = request(server, path, data, token='wrong')
        assert status == 401
        assert TOKEN not in json.dumps(body)
        assert 'Access-Control-Allow-Origin' not in headers
    assert request(server, '/v1/events', headers={'Origin': 'https://evil.test'})[0] == 403
    assert handler.calls.empty()


def test_messages_new_chat_and_callback_are_serialized(companion):
    server, handler = companion
    assert request(server, '/v1/messages', {'text': 'مرحبا'}, request_id='message_001')[0] == 202
    assert request(server, '/v1/new-chat', {}, request_id='newchat_001')[0] == 202
    assert request(server, '/v1/approvals', {'token': 'opaque_nonce_123', 'approve': False}, request_id='cancel_001')[0] == 202
    assert [handler.calls.get(timeout=2) for _ in range(3)] == [
        ('text', 'مرحبا'), ('text', '/new'), ('callback', 'cancel:opaque_nonce_123')]
    assert request(server, '/v1/approvals', {'token': 'opaque_nonce_123', 'approve': True}, request_id='approve_001')[0] == 202
    assert handler.calls.get(timeout=2) == ('callback', 'approve:opaque_nonce_123')


def test_duplicate_request_returns_same_job_and_conflict_rejected(companion):
    server, handler = companion
    first = request(server, '/v1/messages', {'text': 'prepare ZIP'})
    retry = request(server, '/v1/messages', {'text': 'prepare ZIP'})
    assert first[0] == retry[0] == 202
    assert first[1]['job_id'] == retry[1]['job_id']
    assert retry[1]['duplicate']
    assert handler.calls.get(timeout=2) == ('text', 'prepare ZIP')
    assert handler.calls.empty()
    assert request(server, '/v1/messages', {'text': 'other instruction'})[0] == 409


def test_event_polling_is_replayable_and_buttons_have_opaque_token(companion):
    server, _ = companion
    server.send_message(0, 'First')
    server.send_message(0, 'Review these files', {'inline_keyboard': [[
        {'text': 'Approve', 'callback_data': 'approve:opaque_nonce_123'},
        {'text': 'Cancel', 'callback_data': 'cancel:opaque_nonce_123'},
    ]], 'expires_at': 123456789})
    result = request(server, '/v1/events?after=0')[1]
    assert result == request(server, '/v1/events?after=0')[1]
    assert result['cursor'] == 2
    assert result['events'][1]['token'] == 'opaque_nonce_123'
    assert result['events'][1]['expires_at'] == 123456789
    assert result['events'][1]['type'] == 'approval'
    assert TOKEN not in json.dumps(result)
    assert request(server, '/v1/events?after=2')[1]['events'] == []
    assert request(server, '/v1/events?after=999')[1]['reset']


def test_uploaded_zip_has_random_confined_name_and_duplicates_cleaned(companion):
    server, handler = companion
    payload = make_zip()
    headers = {'Content-Type': 'application/zip', 'X-Request-ID': 'upload_001', 'X-Filename': '../../evil.zip'}
    assert request(server, '/v1/uploads', raw=payload, headers=headers)[0] == 202
    kind, path = handler.calls.get(timeout=2)
    assert kind == 'document'
    assert path.parent == server.inbox
    assert path.name != 'evil.zip'
    assert path.read_bytes() == payload
    assert request(server, '/v1/uploads', raw=payload, headers=headers)[1]['duplicate']
    assert list(server.inbox.iterdir()) == [path]
    assert handler.calls.empty()


def test_invalid_payload_and_oversized_upload_are_rejected(companion):
    server, handler = companion
    assert request(server, '/v1/messages', {'text': ''})[0] == 400
    assert request(server, '/v1/messages', {'text': 'x' * 6001})[0] == 400
    assert request(server, '/v1/approvals', {'token': 'opaque_nonce_123', 'approve': 'yes'})[0] == 400
    assert request(server, '/v1/new-chat', {'execute': True})[0] == 400
    assert request(server, '/v1/messages', {'text': 'x'}, request_id='')[0] == 400
    assert request(server, '/v1/uploads', raw=b'not a zip', headers={
        'Content-Type': 'application/zip', 'X-Request-ID': 'upload_bad1'})[0] == 400
    assert not list(server.inbox.iterdir())
    assert request(server, '/v1/uploads', raw=b'x', headers={
        'Content-Type': 'application/zip', 'Content-Length': str(MAX_UPLOAD_BYTES + 1),
        'X-Request-ID': 'upload_big1'})[0] == 413
    assert request(server, '/v1/events?after=bad')[0] == 400
    assert handler.calls.empty()


def test_stopping_invalidates_handler_and_discards_queued_tasks(tmp_path):
    class Blocking(Assistant):
        def __init__(self):
            super().__init__()
            self.started = threading.Event()
            self.release = threading.Event()
        def text(self, text):
            self.started.set()
            self.release.wait(3)
            self.calls.put(('text', text))

    handler = Blocking()
    server = MobileServer(TOKEN, handler, tmp_path, port=0)
    server.start()
    assert request(server, '/v1/messages', {'text': 'running'}, request_id='running_01')[0] == 202
    assert handler.started.wait(2)
    assert request(server, '/v1/messages', {'text': 'queued'}, request_id='queued_001')[0] == 202
    server.stop()
    handler.release.set()
    server._worker.join(timeout=2)
    assert handler.closed
    assert handler.calls.get(timeout=1) == ('text', 'running')
    assert handler.calls.empty()
    assert server.publish('late event') == {}
    assert 'stopped' in server.status_text()


def test_queue_backpressure_does_not_cache_unaccepted_request(tmp_path):
    class Blocking(Assistant):
        def text(self, text):
            started.set()
            release.wait(3)
    started, release = threading.Event(), threading.Event()
    server = MobileServer(TOKEN, Blocking(), tmp_path, port=0)
    server.start()
    try:
        assert request(server, '/v1/messages', {'text': 'running'}, request_id='running_01')[0] == 202
        assert started.wait(2)
        for index in range(16):
            assert request(server, '/v1/messages', {'text': str(index)}, request_id=f'queued_{index:03}')[0] == 202
        assert request(server, '/v1/messages', {'text': 'overflow'}, request_id='overflow_01')[0] == 429
        assert 'overflow_01' not in server._requests
    finally:
        release.set()
        server.stop()


def test_weak_token_is_not_accepted(tmp_path):
    with pytest.raises(MobileServerError):
        MobileServer('short', Assistant(), tmp_path)


def test_events_paginate_by_utf8_byte_limit(companion):
    server, _ = companion
    from yaa_lite.remote.mobile import MAX_EVENTS_RESPONSE_BYTES
    for index in range(12):
        server.publish('ش' * 60000 + str(index))
    first = request(server, '/v1/events?after=0')[1]
    assert 0 < len(first['events']) < 12
    assert len(json.dumps(first, ensure_ascii=False).encode('utf-8')) <= MAX_EVENTS_RESPONSE_BYTES
    assert first['cursor'] == first['events'][-1]['id']
    second = request(server, '/v1/events?after=' + str(first['cursor']))[1]
    assert second['events'][0]['id'] == first['cursor'] + 1
    assert first['events'] + second['events'] == list(server._events)


def test_clear_approval_is_replayed_to_phone(companion):
    server, _ = companion
    server.publish('Review', approval_token='opaque_nonce_123')
    server.publish('', clear_approval=True)
    events = request(server, '/v1/events?after=0')[1]['events']
    assert events[-1]['clear_approval'] is True
    assert events[-1]['type'] == 'message'
    assert events[-1]['text'] == ''
