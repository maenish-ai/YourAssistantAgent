"""Pairing credentials stay local and launch lifecycle remains opt-in."""
from pathlib import Path
import sys
from types import ModuleType, SimpleNamespace

import pytest

from yaa_lite.config import Settings
from yaa_lite.remote.settings import (
    TOKEN_FILE, generate_remote_token, load_remote_token, save_remote_token,
)
from yaa_lite.security.manager import SecurityManager, SecurityError
from yaa_lite.ui.app import App
from yaa_lite.ui.settings_view import SettingsView


@pytest.fixture
def security(tmp_path):
    manager = SecurityManager(tmp_path / 'security')
    manager.setup('', mode='none')
    return manager


def test_pairing_credentials_are_encrypted_and_survive_unlock(security):
    token = generate_remote_token(security)
    encrypted = (security.root / TOKEN_FILE).read_bytes()
    assert token.encode() not in encrypted
    assert encrypted.startswith(b'YAA2')
    assert load_remote_token(security) == token
    fresh = SecurityManager(security.root)
    with pytest.raises(SecurityError):
        load_remote_token(fresh)
    fresh.unlock_without_password()
    assert load_remote_token(fresh) == token
    assert generate_remote_token(fresh) != token


def test_bad_token_or_corrupt_ciphertext_never_echoes_secret(security):
    malicious = 'token-secret-is-invalid'
    with pytest.raises(ValueError) as caught:
        save_remote_token(security, malicious)
    assert malicious not in str(caught.value)
    (security.root / TOKEN_FILE).write_bytes(malicious.encode())
    with pytest.raises(SecurityError) as caught:
        load_remote_token(security)
    assert malicious not in str(caught.value)


def test_no_remote_connection_by_default_and_no_plaintext_pairing_setting():
    settings = Settings()
    assert not settings.remote_enabled
    assert settings.remote_port == 8766
    assert 'remote_token' not in Settings.__dataclass_fields__
    assert 'pairing_token' not in Settings.__dataclass_fields__


def settings_view(settings, security, values):
    class Variable:
        def __init__(self, value): self.value = value
        def get(self): return self.value
        def set(self, value): self.value = value
    saved, statuses = [], []
    view = SimpleNamespace(
        settings=settings, security=security, on_save=saved.append,
        vars={k: Variable(v) for k, v in values.items()},
        status=SimpleNamespace(configure=lambda **kwargs: statuses.append(kwargs['text'])),
        t=lambda ar, en: en, _refresh_remote_status=lambda: None,
    )
    view._value = lambda name, default=None: SettingsView._value(view, name, default)
    return view, saved, statuses


def test_remote_settings_validate_then_save_without_token_in_json(tmp_path, monkeypatch, security):
    import yaa_lite.config as config
    monkeypatch.setattr(config, 'config_dir', lambda: tmp_path)
    token = generate_remote_token(security)
    checkout = tmp_path / 'checkout'
    checkout.mkdir()
    view, saved, statuses = settings_view(Settings(), security, {
        'remote_enabled': True, 'remote_port': '8767',
        'github_repository': 'example/assistant', 'github_checkout': str(checkout),
    })
    SettingsView._save_remote_settings(view)
    assert len(saved) == 1
    assert saved[0].remote_port == 8767
    assert saved[0].github_checkout == str(checkout.resolve())
    stored = (tmp_path / 'settings.json').read_text()
    assert token not in stored
    assert Settings.load().remote_enabled
    assert statuses[-1] == 'Saved'


@pytest.mark.parametrize('values', [
    {'remote_enabled': True},  # Missing pairing token.
    {'remote_enabled': False, 'remote_port': 'not-a-number'},
    {'remote_enabled': False, 'remote_port': '80'},
    {'remote_enabled': False, 'github_repository': '../outside'},
])
def test_invalid_remote_settings_leave_existing_configuration_unchanged(values, security, tmp_path, monkeypatch):
    import yaa_lite.config as config
    monkeypatch.setattr(config, 'config_dir', lambda: tmp_path)
    settings = Settings()
    view, saved, statuses = settings_view(settings, security, values)
    SettingsView._save_remote_settings(view)
    assert saved == []
    assert not settings.remote_enabled
    assert not (tmp_path / 'settings.json').exists()
    assert statuses


def app_stub(settings):
    statuses = []
    app = SimpleNamespace(
        settings_obj=settings, remote_worker=None, security=object(), db=object(),
        runtime=object(), facebook=object(), t=lambda ar, en: en,
        _activity=lambda kind, detail: statuses.append((kind, detail)),
    )
    app._stop_remote_worker = lambda: App._stop_remote_worker(app)
    return app, statuses


def test_worker_is_opt_in_restarted_and_stopped(monkeypatch):
    starts, stops = [], []
    class Worker:
        def start(self): starts.append(self)
        def stop(self): stops.append(self)
        def status_text(self): return 'listening on localhost'
    module = ModuleType('yaa_lite.remote.service')
    module.build_remote_worker = lambda *args, **kwargs: Worker()
    monkeypatch.setitem(sys.modules, 'yaa_lite.remote.service', module)
    app, statuses = app_stub(Settings())
    App._restart_remote_worker(app)
    assert starts == []
    app.settings_obj.remote_enabled = True
    App._restart_remote_worker(app)
    first = app.remote_worker
    assert App.remote_status_text(app) == 'listening on localhost'
    App._restart_remote_worker(app)
    assert stops == [first]
    assert len(starts) == 2
    app.settings_obj.remote_enabled = False
    App._restart_remote_worker(app)
    assert len(stops) == 2
    assert app.remote_worker is None


def test_worker_start_failure_is_sanitized(monkeypatch):
    secret = 'secret-pairing-token'
    module = ModuleType('yaa_lite.remote.service')
    def broken(*args, **kwargs): raise RuntimeError('unsafe URL contains ' + secret)
    module.build_remote_worker = broken
    monkeypatch.setitem(sys.modules, 'yaa_lite.remote.service', module)
    app, statuses = app_stub(Settings(remote_enabled=True))
    App._restart_remote_worker(app)
    assert secret not in App.remote_status_text(app)
    assert all(secret not in detail for _, detail in statuses)
    assert app.remote_worker is None


def test_config_rejects_non_boolean_remote_opt_in_and_invalid_port(tmp_path, monkeypatch):
    import json
    import yaa_lite.config as config
    monkeypatch.setattr(config, 'config_dir', lambda: tmp_path)
    path = tmp_path / 'settings.json'
    path.write_text(json.dumps({'remote_enabled': 'true', 'remote_port': 8766}))
    assert not Settings.load().remote_enabled
    path.write_text(json.dumps({'remote_enabled': True, 'remote_port': 'bad'}))
    loaded = Settings.load()
    assert not loaded.remote_enabled
    assert loaded.remote_port == 8766
