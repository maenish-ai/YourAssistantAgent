from yaa_lite.remote.files import RemoteFiles
from yaa_lite.remote.desktop_agent import _find_recent_uploads, tools
import os


def test_recent_phone_upload_discovery_is_bounded_and_real(tmp_path):
    (tmp_path / 'inbox').mkdir()
    (tmp_path / 'inbox' / 'campaign.zip').write_bytes(b'zip')
    (tmp_path / 'other.txt').write_text('hello')
    result = _find_recent_uploads(RemoteFiles(tmp_path), 'campaign')
    assert result['entries'] == [{'name':'campaign.zip', 'path':'inbox/campaign.zip', 'size':3}]
    assert result['folders_checked'] == 2


def test_missing_phone_file_not_invented(tmp_path):
    assert _find_recent_uploads(RemoteFiles(tmp_path), 'absent')['entries'] == []


def test_tool_is_exposed_to_agent():
    assert 'find_recent_uploads' in [x['function']['name'] for x in tools()]


def test_recorded_phone_upload_beats_newer_unrelated_file(tmp_path):
    received = tmp_path / 'received.zip'
    received.write_bytes(b'phone')
    stat = received.stat()
    recorded = [{'path':'received.zip', 'size':stat.st_size, 'mtime_ns':stat.st_mtime_ns}]
    other = tmp_path / 'unrelated.zip'
    other.write_bytes(b'other')
    os.utime(other, ns=(stat.st_mtime_ns + 1_000_000_000, stat.st_mtime_ns + 1_000_000_000))
    result = _find_recent_uploads(RemoteFiles(tmp_path), phone_uploads=recorded)
    assert result['source_verified'] is True
    assert [e['name'] for e in result['entries']] == ['received.zip']


def test_changed_phone_file_is_only_unverified_candidate(tmp_path):
    received = tmp_path / 'received.zip'
    received.write_bytes(b'original')
    stat = received.stat()
    recorded = [{'path':'received.zip', 'size':stat.st_size, 'mtime_ns':stat.st_mtime_ns}]
    received.write_bytes(b'changed file size')
    result = _find_recent_uploads(RemoteFiles(tmp_path), phone_uploads=recorded)
    assert result['source_verified'] is False
    assert 'unverified' in result['note']
