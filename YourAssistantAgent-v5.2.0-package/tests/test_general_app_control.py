"""Observed shortcut launches across arbitrary names, not a fixed application list."""
from contextlib import contextmanager
from dataclasses import replace
from pathlib import Path
import os
import time

import pytest

from yaa_lite.remote.desktop import DesktopError, WindowsDesktop


@pytest.fixture
def applications(tmp_path, monkeypatch):
    personal = tmp_path/'Personal'
    common = tmp_path/'Common'
    personal.mkdir();common.mkdir()
    (personal/'Tools').mkdir()
    (personal/'Tools'/'محرر عربي.lnk').write_bytes(b'personal shortcut')
    (common/'محرر عربي.lnk').write_bytes(b'common shortcut')
    (common/'Arbitrary Designer.lnk').write_bytes(b'arbitrary shortcut')
    (common/'do-not-run.cmd').write_text('unobserved command')
    desktop = WindowsDesktop(lambda: True)
    @contextmanager
    def session():
        if not desktop.enabled() or desktop._revoked:
            raise DesktopError('Control disabled')
        yield None
    monkeypatch.setattr(desktop, '_session', session)
    monkeypatch.setattr(desktop, '_application_roots', lambda: [personal, common])
    calls=[]
    monkeypatch.setattr(os, 'startfile', calls.append, raising=False)
    return desktop, personal, common, calls


def test_duplicate_names_return_distinct_observed_ids_and_launch_exact_shortcut(applications):
    desktop, personal, common, calls = applications
    rows = desktop.list_applications('محرر')['applications']
    assert len(rows) == 2 and len({row['id'] for row in rows}) == 2
    assert {row['location'] for row in rows} == {'محرر عربي.lnk', 'Tools/محرر عربي.lnk'}
    selected = next(row for row in rows if row['location'].startswith('Tools/'))
    result = desktop.launch_application(selected['id'])
    assert calls == [str(personal/'Tools'/'محرر عربي.lnk')]
    assert result['ok'] and 'أُرسل طلب' in result['result']
    assert 'do-not-run' not in str(desktop.list_applications())


def test_launch_requires_observed_unexpired_unchanged_id(applications):
    desktop, _, common, calls = applications
    with pytest.raises(DesktopError):
        desktop.launch_application(str(common/'Arbitrary Designer.lnk'))
    row = desktop.list_applications('Designer')['applications'][0]
    identifier = row['id']
    desktop._applications[identifier] = replace(desktop._applications[identifier], observed_at=time.monotonic()-121)
    with pytest.raises(DesktopError):
        desktop.launch_application(identifier)
    row = desktop.list_applications('Designer')['applications'][0]
    path = common/'Arbitrary Designer.lnk'
    original = path.stat()
    # Even preserving name, length and mtime cannot reuse a changed shortcut.
    path.write_bytes(b'x' * original.st_size)
    os.utime(path, ns=(original.st_atime_ns, original.st_mtime_ns))
    with pytest.raises(DesktopError, match='تغيّر'):
        desktop.launch_application(row['id'])
    assert calls == []


def test_filesystem_link_cannot_redirect_observed_shortcut(applications, tmp_path):
    desktop, _, common, calls = applications
    outside = tmp_path/'outside.lnk';outside.write_bytes(b'other shortcut')
    try:
        (common/'linked.lnk').symlink_to(outside)
    except OSError:
        pytest.skip('Filesystem links unavailable')
    assert desktop.list_applications('linked')['applications'] == []
    row = desktop.list_applications('Designer')['applications'][0]
    path = common/'Arbitrary Designer.lnk';path.unlink();path.symlink_to(outside)
    with pytest.raises(DesktopError):
        desktop.launch_application(row['id'])
    assert calls == []


def test_permissions_are_rechecked_before_launch_and_folder_open(applications):
    desktop, _, common, calls = applications
    row = desktop.list_applications('Designer')['applications'][0]
    desktop.enabled = lambda: False
    with pytest.raises(DesktopError):desktop.launch_application(row['id'])
    with pytest.raises(DesktopError):desktop.open_folder(common)
    with pytest.raises(DesktopError):desktop.list_applications()
    assert calls == []


def test_application_pagination_keeps_prior_observed_ids(applications):
    desktop, _, common, calls = applications
    for index in range(45):(common/f'Tool {index:02}.lnk').write_bytes(str(index).encode())
    first = desktop.list_applications('Tool')
    second = desktop.list_applications('Tool', first['next_offset'])
    assert len(first['applications']) == 10 and len(second['applications']) == 10
    second = desktop.list_applications('Tool', 40)
    assert second['next_offset'] is None
    desktop.launch_application(first['applications'][0]['id'])
    assert calls == [str(common/'Tool 00.lnk')]


def test_open_folder_sends_exact_existing_directory_without_command_arguments(applications):
    desktop, personal, common, calls = applications
    folder = common/'Folder with spaces';folder.mkdir()
    result = desktop.open_folder(folder)
    assert result['ok'] and calls == [str(folder)]
    with pytest.raises(DesktopError):desktop.open_folder(common/'Arbitrary Designer.lnk')
    with pytest.raises(DesktopError):desktop.open_folder(common/'Missing')
    assert calls == [str(folder)]


def test_windows_launch_refusal_is_a_failure_not_an_opened_application(applications, monkeypatch):
    desktop, _, _, calls = applications
    row = desktop.list_applications('Designer')['applications'][0]
    def refused(path):
        raise OSError('system-specific error')
    monkeypatch.setattr(os, 'startfile', refused)
    with pytest.raises(DesktopError, match='رفض Windows'):
        desktop.launch_application(row['id'])
    assert calls == []
