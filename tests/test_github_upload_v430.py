"""Local safety regression tests: no real network/authentication is used."""
from pathlib import Path
from unittest.mock import patch
import subprocess
import os
import zipfile
import pytest

from yaa_lite.github_upload_v430 import (
    GitHubUploadError, PENDING_UPLOAD_KEY, PENDING_UPLOAD_REPO_KEY, _zip_members, _validate_name, describe_plan,
    is_upload_request, prepare_upload, prepare_configured_upload, publish_upload, validate_repository,
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
    assert pushes == [('push', 'origin', f'{git(checkout, "rev-parse", "HEAD")}:refs/heads/main')]
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
                                 '.git/config', 'src/../../evil',
                                 '.env', 'secrets.json', 'foo/CON.txt', 'foo/id_rsa'])
def test_invalid_zip_path(tmp_path, bad):
    path = make_zip(tmp_path / 'patch.zip', {bad: 'bad'})
    with pytest.raises(GitHubUploadError):
        _zip_members(path)


def test_reject_backslash_path_independent_of_zipfile_windows_normalization(tmp_path):
    # zipfile.ZipInfo replaces backslashes with '/' on Windows. Testing the
    # archive alone would silently test 'src/evil' (which is safe) instead of
    # the intended raw 'src\\evil'. Assert the validator separately so
    # this remains a meaningful cross-platform security regression test.
    with pytest.raises(GitHubUploadError, match='unsafe path'):
        _validate_name('src\\evil')

    archive = make_zip(tmp_path / 'backslash.zip', {'src\\evil': 'bad'})
    with zipfile.ZipFile(archive) as z:
        parsed_name = z.namelist()[0]
    if parsed_name == 'src/evil':
        # Expected normalization on Windows, still confined to the repository.
        assert _zip_members(archive)[0][1] == 'src/evil'
    else:
        assert parsed_name == 'src\\evil'
        with pytest.raises(GitHubUploadError, match='unsafe path'):
            _zip_members(archive)


def test_reject_duplicate_case_insensitive(tmp_path):
    path = make_zip(tmp_path / 'patch.zip', {'SRC/File.py': 'x', 'src/file.py': 'y'})
    with pytest.raises(GitHubUploadError, match='duplicate'):
        _zip_members(path)


def test_upload_requests_only():
    assert is_upload_request('ارفع ملف ZIP على GitHub')
    assert is_upload_request('اعمل push إلى المستودع')
    assert is_upload_request('ارفع الملف على جيت هب ديسكتوب')
    assert is_upload_request('بدي ترفع هاد على جيتهب')
    assert is_upload_request('ارفعه على جيت هاب')
    assert not is_upload_request('كيف أرفع ملف ZIP إلى GitHub؟')
    assert not is_upload_request('كيف أرفع على جيت هب؟')
    assert not is_upload_request('انشر على الفيسبوك')


def test_github_download_wrapper_is_removed(checkout, tmp_path):
    archive = make_zip(tmp_path / 'download.zip', {
        'YourAssistantAgent-main/README.md': 'after',
        'YourAssistantAgent-main/requirements.txt': 'requests',
        'YourAssistantAgent-main/README_AR.txt': 'شرح',
    })
    plan = prepare_upload(archive, checkout)
    assert [f.relative_path for f in plan.files] == [
        'README.md', 'requirements.txt', 'README_AR.txt',
    ]


@pytest.mark.parametrize('normalized_only', [False, True])
def test_publish_handles_git_line_ending_normalization(checkout, tmp_path, normalized_only):
    (checkout / '.gitattributes').write_text('*.txt text eol=lf\n', encoding='utf-8')
    (checkout / 'notes.txt').write_bytes(b'hello\n')
    git(checkout, 'add', '--', '.gitattributes', 'notes.txt')
    git(checkout, 'commit', '-m', 'configure line endings')
    before = git(checkout, 'rev-parse', 'HEAD')
    contents = {'notes.txt': b'hello\r\n'}
    if not normalized_only:
        contents['README.md'] = 'after'
    archive = make_zip(tmp_path / 'patch.zip', contents)
    plan = prepare_upload(archive, checkout)
    import yaa_lite.github_upload_v430 as m
    original_git = m._git
    pushes = []

    def fake_git(executable, root, *args, **kwargs):
        if args[0] == 'push':
            pushes.append(args)
            return ''
        return original_git(executable, root, *args, **kwargs)

    with patch.object(m, '_git', side_effect=fake_git):
        result = publish_upload(plan, approved=True)
    assert git(checkout, 'status', '--porcelain') == ''
    if normalized_only:
        assert 'No commit or push needed' in result
        assert git(checkout, 'rev-parse', 'HEAD') == before
        assert not pushes
    else:
        assert 'Published 1 files' in result
        assert len(pushes) == 1
        assert git(checkout, 'show', 'HEAD:README.md') == 'after'


def test_publish_file_with_leading_space_to_local_remote(checkout, tmp_path):
    # Perform a real push without contacting GitHub or requiring credentials.
    remote = tmp_path / 'remote.git'
    subprocess.check_output(['git', 'init', '--bare', str(remote)])
    archive = make_zip(tmp_path / 'patch.zip', {' leading.py': 'print(1)\n'})
    plan = prepare_upload(archive, checkout)
    import yaa_lite.github_upload_v430 as m
    original_git = m._git

    def local_push(executable, root, *args, **kwargs):
        if args[0] == 'push':
            assert args[1] == 'origin'
            return original_git(executable, root, 'push', str(remote), *args[2:], **kwargs)
        return original_git(executable, root, *args, **kwargs)

    with patch.object(m, '_git', side_effect=local_push):
        assert 'Published 1 files' in publish_upload(plan, approved=True)
    assert git(remote, 'show', 'main: leading.py') == 'print(1)'


def test_failed_push_can_retry_without_duplicate_commit(checkout, tmp_path):
    archive = make_zip(tmp_path / 'patch.zip', {'README.md': 'after'})
    plan = prepare_upload(archive, checkout)
    import yaa_lite.github_upload_v430 as m
    original_git = m._git

    def failed_push(executable, root, *args, **kwargs):
        if args[0] == 'push':
            raise GitHubUploadError('network unavailable')
        return original_git(executable, root, *args, **kwargs)

    with patch.object(m, '_git', side_effect=failed_push):
        with pytest.raises(GitHubUploadError, match='PUSH FAILED'):
            publish_upload(plan, approved=True)
    local_commit = git(checkout, 'rev-parse', 'HEAD')
    assert git(checkout, 'config', '--get', PENDING_UPLOAD_KEY) == f'main:{local_commit}'
    retry = prepare_upload(archive, checkout)
    assert not retry.changes
    assert retry.pending_commit == local_commit
    assert 'Pending upload commit:' in describe_plan(retry)
    assert 'no new commit will be created' in describe_plan(retry)
    with pytest.raises(GitHubUploadError, match='explicit user approval'):
        publish_upload(retry)

    remote = tmp_path / 'retry-remote.git'
    subprocess.check_output(['git', 'init', '--bare', str(remote)])

    def local_push(executable, root, *args, **kwargs):
        if args[0] == 'push':
            return original_git(executable, root, 'push', str(remote), *args[2:], **kwargs)
        return original_git(executable, root, *args, **kwargs)

    with patch.object(m, '_git', side_effect=local_push):
        assert 'Published pending upload' in publish_upload(retry, approved=True)
    assert git(checkout, 'rev-parse', 'HEAD') == local_commit
    assert git(remote, 'rev-parse', 'main') == local_commit
    assert git(checkout, 'config', '--default', '', '--get', PENDING_UPLOAD_KEY) == ''
    assert not prepare_upload(archive, checkout).pending_commit


def test_pending_upload_is_bound_to_branch_and_commit(checkout, tmp_path):
    archive = make_zip(tmp_path / 'patch.zip', {'README.md': 'before'})
    head = git(checkout, 'rev-parse', 'HEAD')
    git(checkout, 'config', '--local', PENDING_UPLOAD_KEY, f'main:{head}')
    assert prepare_upload(archive, checkout).pending_commit == head
    git(checkout, 'checkout', '-b', 'other')
    assert not prepare_upload(archive, checkout).pending_commit
    git(checkout, 'checkout', 'main')
    git(checkout, 'commit', '--allow-empty', '-m', 'different head')
    assert not prepare_upload(archive, checkout).pending_commit


@pytest.mark.skipif(os.name == "nt", reason="Windows symlink permission varies across runners")
def test_refuse_symlink_destination(checkout, tmp_path):
    archive = make_zip(tmp_path / 'patch.zip', {'src/demo.py': 'x'})
    (checkout / 'src').symlink_to(tmp_path, target_is_directory=True)
    git(checkout, 'add', '--', 'src')
    git(checkout, 'commit', '-m', 'track symlink')
    with pytest.raises(GitHubUploadError, match='symbolic link'):
        prepare_upload(archive, checkout)


@pytest.mark.parametrize('repository', ['', 'https://github.com/owner/repo', 'owner', '../repo',
                                      'owner/../repo', 'owner/..', '-owner/repo', 'owner/repo?x=y'])
def test_repository_setting_is_a_name_not_url_or_path(repository):
    with pytest.raises(GitHubUploadError, match='owner/name'):
        validate_repository(repository)


@pytest.mark.parametrize('remote', ['https://github.com/example/OtherProject.git',
                                   'git@github.com:example/OtherProject.git',
                                   'ssh://git@github.com/example/OtherProject.git'])
def test_configurable_target_preview_and_publish(checkout, tmp_path, remote):
    git(checkout, 'remote', 'set-url', 'origin', remote)
    archive = make_zip(tmp_path / 'patch.zip', {'OtherProject-main/styles.css': 'body{}'})
    plan = prepare_upload(archive, checkout, expected_repo='example/OtherProject')
    assert plan.expected_repo == 'example/OtherProject'
    assert plan.changes[0].relative_path == 'styles.css'
    assert 'Repository: example/OtherProject' in describe_plan(plan)
    import yaa_lite.github_upload_v430 as module
    original_git = module._git
    def fake_push(executable, root, *args, **kwargs):
        if args[0] == 'push':
            return ''
        return original_git(executable, root, *args, **kwargs)
    with patch.object(module, '_git', side_effect=fake_push):
        result = publish_upload(plan, approved=True)
    assert 'https://github.com/example/OtherProject/commit/' in result


def test_remote_change_after_preview_is_rejected(checkout, tmp_path):
    archive = make_zip(tmp_path / 'patch.zip', {'README.md': 'after'})
    plan = prepare_upload(archive, checkout)
    git(checkout, 'remote', 'set-url', 'origin', 'https://github.com/elsewhere/project.git')
    with pytest.raises(GitHubUploadError, match='not the expected'):
        publish_upload(plan, approved=True)
    assert (checkout / 'README.md').read_text() == 'before'


@pytest.mark.parametrize('push_urls', [
    ['https://github.com/elsewhere/project.git'],
    ['https://other.example/maenish-ai/YourAssistantAgent.git'],
    ['https://github.com/maenish-ai/YourAssistantAgent.git', 'https://github.com/elsewhere/project.git'],
])
def test_separate_or_multiple_push_destinations_cannot_bypass_target(checkout, tmp_path, push_urls):
    for remote in push_urls:
        git(checkout, 'config', '--add', 'remote.origin.pushurl', remote)
    archive = make_zip(tmp_path / 'patch.zip', {'README.md': 'after'})
    with pytest.raises(GitHubUploadError, match='not the expected'):
        prepare_upload(archive, checkout)


def test_pending_upload_cannot_follow_reconfigured_repository(checkout, tmp_path):
    archive = make_zip(tmp_path / 'patch.zip', {'README.md': 'before'})
    head = git(checkout, 'rev-parse', 'HEAD')
    git(checkout, 'config', '--local', PENDING_UPLOAD_KEY, f'main:{head}')
    git(checkout, 'config', '--local', PENDING_UPLOAD_REPO_KEY, 'maenish-ai/YourAssistantAgent')
    git(checkout, 'remote', 'set-url', 'origin', 'https://github.com/example/OtherProject.git')
    assert not prepare_upload(archive, checkout, expected_repo='example/OtherProject').pending_commit


def test_new_chat_reuses_persisted_checkout_without_picker(checkout, tmp_path):
    import json
    from types import SimpleNamespace
    settings_file = tmp_path / 'settings.json'
    settings = SimpleNamespace(github_repository='maenish-ai/YourAssistantAgent', github_checkout='')
    def save():
        settings_file.write_text(json.dumps({'github_repository': settings.github_repository,
                                            'github_checkout': settings.github_checkout}))
    settings.save = save
    archive = make_zip(tmp_path / 'patch.zip', {'README.md': 'after'})
    first = prepare_configured_upload(archive, settings, lambda: checkout)
    fresh = SimpleNamespace(**json.loads(settings_file.read_text()), save=lambda: None)
    def no_picker():
        raise AssertionError('A fresh chat must use the saved target')
    second = prepare_configured_upload(archive, fresh, no_picker)
    assert first.checkout == second.checkout == checkout.resolve()
    assert (checkout / 'README.md').read_text() == 'before'


def test_remote_upload_requires_preconfigured_checkout(tmp_path):
    from types import SimpleNamespace
    settings = SimpleNamespace(github_repository='maenish-ai/YourAssistantAgent', github_checkout='')
    archive = make_zip(tmp_path / 'patch.zip', {'README.md': 'after'})
    with pytest.raises(GitHubUploadError, match='Configure the local GitHub checkout'):
        prepare_configured_upload(archive, settings)


def test_invalid_chosen_checkout_is_not_remembered(checkout, tmp_path):
    from types import SimpleNamespace
    settings = SimpleNamespace(github_repository='someone/Other', github_checkout='',
                               save=lambda: (_ for _ in ()).throw(AssertionError('invalid target saved')))
    archive = make_zip(tmp_path / 'patch.zip', {'README.md': 'after'})
    with pytest.raises(GitHubUploadError, match='not the expected'):
        prepare_configured_upload(archive, settings, lambda: checkout)
    assert settings.github_checkout == ''
