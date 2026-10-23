"""Local safety regression tests: no real network/authentication is used."""
from pathlib import Path
from unittest.mock import patch
import subprocess
import os
import zipfile
import pytest

from yaa_lite.github_upload_v430 import (
    GitHubUploadError, _zip_members, describe_plan,
    is_upload_request, prepare_upload, publish_upload,
)


def git(cwd, *args):
    return subprocess.check_output(['git', '-C', str(cwd), *args], text=True).strip()


@pytest.fixture
def checkout(tmp_path):
    root = tmp_path / 'YourAssistantAgent'
    root.mkdir()
    git(root, 'init', '-b', 'main')
    git(root, 'config', 'user.email', 'upload-tests@example.invalid')
    git(root, 'config', 'user.name', 'YAA test')
    (root / 'README.md').write_text('before', encoding='utf-8')
    git(root, 'add', '--', 'README.md')
    git(root, 'commit', '-m', 'initial')
    git(root, 'remote', 'add', 'origin', 'https://github.com/maenish-ai/YourAssistantAgent.git')
    return root


def make_zip(path, mapping):
    with zipfile.ZipFile(path, 'w') as z:
        for name, content in mapping.items():
            z.writestr(name, content)
    return path


def test_preview_no_mutation_without_approval(checkout, tmp_path):
    archive = make_zip(tmp_path / 'patch.zip', {'YourAssistantAgent/README.md': 'after',
                                                  'YourAssistantAgent/src/sample.py': 'print(1)'})
    head = git(checkout, 'rev-parse', 'HEAD')
    plan = prepare_upload(archive, checkout)
    assert [(x.relative_path, x.change) for x in plan.changes] == [('README.md', 'modified'), ('src/sample.py', 'added')]
    assert 'Target branch: main' in describe_plan(plan)
    assert git(checkout, 'rev-parse', 'HEAD') == head
    assert (checkout / 'README.md').read_text() == 'before'
    with pytest.raises(GitHubUploadError, match='explicit user approval'):
        publish_upload(plan)
    assert not (checkout / 'src').exists()


def test_publish_commits_and_calls_push_once(checkout, tmp_path):
    archive = make_zip(tmp_path / 'patch.zip', {'src/demo.py': 'print("yes")', 'README.md': 'after'})
    plan = prepare_upload(archive, checkout)
    import yaa_lite.github_upload_v430 as m
    original_git = m._git
    pushes = []
    def fake_git(executable, root, *args, **kwargs):
        if args and args[0] == 'push':
            pushes.append(args)
            return ''
        return original_git(executable, root, *args, **kwargs)
    with patch.object(m, '_git', side_effect=fake_git):
        result = publish_upload(plan, approved=True)
    assert 'Published 2 files' in result
    assert pushes == [('push', 'origin', 'HEAD:refs/heads/main')]
    assert git(checkout, 'show', 'HEAD:README.md') == 'after'
    assert git(checkout, 'show', 'HEAD:src/demo.py') == 'print("yes")'


def test_modified_repo_blocks_publishing(checkout, tmp_path):
    archive = make_zip(tmp_path / 'patch.zip', {'README.md': 'after'})
    plan = prepare_upload(archive, checkout)
    (checkout / 'README.md').write_text('someone else modified this', encoding='utf-8')
    with pytest.raises(GitHubUploadError, match='uncommitted'):
        publish_upload(plan, approved=True)


def test_reject_wrong_origin(checkout, tmp_path):
    git(checkout, 'remote', 'set-url', 'origin', 'https://github.com/someone/Other.git')
    archive = make_zip(tmp_path / 'patch.zip', {'README.md': 'after'})
    with pytest.raises(GitHubUploadError, match='not the expected'):
        prepare_upload(archive, checkout)


@pytest.mark.parametrize('bad', ['../escape.py', '/root/file.py', 'C:/windows/file.py',
                                 '.git/config', 'src/../../evil', 'src\\evil',
                                 '.env', 'secrets.json', 'foo/CON.txt', 'foo/id_rsa'])
def test_invalid_zip_path(tmp_path, bad):
    path = make_zip(tmp_path / 'patch.zip', {bad: 'bad'})
    with pytest.raises(GitHubUploadError):
        _zip_members(path)


def test_reject_duplicate_case_insensitive(tmp_path):
    path = make_zip(tmp_path / 'patch.zip', {'SRC/File.py': 'x', 'src/file.py': 'y'})
    with pytest.raises(GitHubUploadError, match='duplicate'):
        _zip_members(path)


def test_upload_requests_only():
    assert is_upload_request('ارفع ملف ZIP على GitHub')
    assert is_upload_request('اعمل push إلى المستودع')
    assert not is_upload_request('كيف أرفع ملف ZIP إلى GitHub؟')
    assert not is_upload_request('انشر على الفيسبوك')


@pytest.mark.skipif(os.name == "nt", reason="Windows symlink permission varies across runners")
def test_refuse_symlink_destination(checkout, tmp_path):
    archive = make_zip(tmp_path / 'patch.zip', {'src/demo.py': 'x'})
    (checkout / 'src').symlink_to(tmp_path, target_is_directory=True)
    git(checkout, 'add', '--', 'src')
    git(checkout, 'commit', '-m', 'track symlink')
    with pytest.raises(GitHubUploadError, match='symbolic link'):
        prepare_upload(archive, checkout)
