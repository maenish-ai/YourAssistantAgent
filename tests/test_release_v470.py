"""New file scope, idle-power lifecycle and real pairing-view regression tests."""
from pathlib import Path
import threading
from types import SimpleNamespace
import pytest
from yaa_lite.remote.files import RemoteFiles, FileError
from yaa_lite.remote.power import AwakeGuard, CONTINUOUS, SYSTEM_REQUIRED


def test_all_drives_are_virtual_and_preserve_file_safety(tmp_path):
    c = tmp_path/'c'; d = tmp_path/'d'; c.mkdir(); d.mkdir()
    (c/'Documents').mkdir(); (d/'photo.jpg').write_bytes(b'photo')
    files = RemoteFiles(tmp_path, all_drives=True, roots={'C': c, 'D': d})
    assert [e['path'] for e in files.listing()['entries']] == ['@drives/C','@drives/D']
    assert not files.listing()['can_upload']
    assert files.listing('@drives/C')['entries'][0]['path'] == '@drives/C/Documents'
    assert files.listing('@drives/C/Documents')['display_path'] == 'C:\\Documents'
    assert files.resolve('@drives/D/photo.jpg', file=True) == d/'photo.jpg'
    source=tmp_path/'source'; source.write_bytes(b'new file')
    assert files.import_file(source,'@drives/C/Documents','file.txt')['path']=='@drives/C/Documents/file.txt'
    assert (c/'Documents/file.txt').read_bytes()==b'new file'
    with pytest.raises(FileError): files.import_file(source,'@drives/C/Documents','file.txt')
    for invalid in ('', '@drives', '@drives/Z', '@drives/C/../d/photo.jpg', '/etc/passwd', 'C:/file'):
        with pytest.raises(FileError): files.resolve(invalid)
    try: (c/'escape').symlink_to(d,target_is_directory=True)
    except OSError: return
    assert 'escape' not in [e['name'] for e in files.listing('@drives/C')['entries']]
    with pytest.raises(FileError): files.resolve('@drives/C/escape/photo.jpg',file=True)


def test_sleep_guard_releases_on_battery_and_stop():
    states=[]; changed=threading.Event(); sleeping=threading.Event(); ac=[True]
    def apply(flags):
        states.append(flags)
        (changed if flags & SYSTEM_REQUIRED else sleeping).set()
    backend=SimpleNamespace(on_ac=lambda:ac[0],set_state=apply)
    guard=AwakeGuard(True,backend=backend,interval=.01)
    guard.start()
    try:
        assert changed.wait(2)
        ac[0]=False
        assert sleeping.wait(2)
    finally: guard.stop()
    assert states[0]==CONTINUOUS|SYSTEM_REQUIRED
    assert states[-1]==CONTINUOUS
    assert not guard.thread.is_alive()
    disabled=AwakeGuard(False,backend=backend);disabled.start()
    assert disabled.thread is None


@pytest.fixture
def pairing_view(tmp_path,monkeypatch):
    import tkinter as tk
    from yaa_lite.ui.app import App
    from yaa_lite.ui.settings_view import SettingsView
    from yaa_lite.config import Settings
    from yaa_lite.security.manager import SecurityManager
    monkeypatch.setattr(Settings,'save',lambda self:None)
    try: root=tk.Tk()
    except tk.TclError: pytest.skip('Tk display unavailable')
    root.geometry('1100x760'); App._styles(root)
    security=SecurityManager(tmp_path/'security');security.setup('',mode='none')
    calls=[];view=SettingsView(root,Settings(interface_language='en'),calls.append,security,remote_status=lambda:'Test relay connecting')
    view.pack(fill='both',expand=True);view.show_category('pairing');root.update()
    try: yield view,security,calls,root
    finally: view.destroy();root.destroy()


def test_pairing_shows_missing_host_without_generating_bogus_qr(pairing_view):
    view,security,calls,root=pairing_view
    assert 'not configured' in view._remote_status_label.cget('text')
    view._show_pairing_qr();root.update()
    assert 'not configured' in view.status.cget('text')
    assert not any(child.cget('image') for child in view._qr_panel.winfo_children())
    assert not calls


def test_pairing_save_applies_permissions_and_displays_qr_in_same_page(pairing_view):
    view,security,calls,root=pairing_view
    view.vars['remote_relay_url'].set('https://relay.example.test')
    view.vars['relay_enrollment_input'].set('E'*48)
    for name in ('remote_desktop_enabled','remote_ai_enabled','remote_files_all_drives','remote_keep_awake'):
        view.vars[name].set(True)
    view.save();root.update()
    assert len(calls)==1
    assert calls[0].remote_connection_mode=='relay' and calls[0].remote_enabled
    assert calls[0].remote_files_all_drives and calls[0].remote_keep_awake
    assert any(child.cget('image') for child in view._qr_panel.winfo_children())
    assert not view.vars['relay_enrollment_input'].get()
    view._disable_phone();assert not calls[-1].remote_enabled
    view.show_category('desktop');root.update()
    view.vars['remote_files_all_drives'].set(False);view.save()
    assert not calls[-1].remote_files_all_drives


def test_invalid_ai_permissions_do_not_persist_new_credentials(pairing_view):
    from yaa_lite.remote.settings import load_remote_token,load_relay_enrollment
    view,security,calls,root=pairing_view
    view.vars['remote_relay_url'].set('https://relay.example.test')
    view.vars['relay_enrollment_input'].set('E'*48)
    view.vars['remote_ai_enabled'].set(True)
    view.save()
    assert not calls and not load_remote_token(security) and not load_relay_enrollment(security)
    assert 'Enable screen' in view.status.cget('text')


def test_hosted_setup_file_is_private_and_never_silently_overwritten(tmp_path):
    import importlib.util
    script=Path(__file__).resolve().parents[1]/'scripts/create_desktop_setup.py'
    spec=importlib.util.spec_from_file_location('create_setup',script);module=importlib.util.module_from_spec(spec);spec.loader.exec_module(module)
    destination=tmp_path/'desktop-setup.json'
    with pytest.raises(ValueError):module.create('http://relay.example.test','X'*48,destination)
    assert not destination.exists()
    module.create('https://relay.example.test','X'*48,destination)
    with pytest.raises(FileExistsError):module.create('https://other.example.test','Y'*48,destination)
    assert 'other.example' not in destination.read_text()
