from yaa_lite.remote.files import RemoteFiles
from yaa_lite.remote.desktop_agent import _find_recent_uploads, tools


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
