"""Ensure build-time voice downloads cannot silently change content."""
import hashlib
import importlib.util
import io
from pathlib import Path
import sys
from types import SimpleNamespace

import pytest


@pytest.fixture
def voice_builder(monkeypatch):
    monkeypatch.setitem(sys.modules, 'onnx', SimpleNamespace())
    script = Path(__file__).resolve().parents[1] / 'tools' / 'prepare_bundled_female_voice.py'
    spec = importlib.util.spec_from_file_location('voice_builder_integrity_test', script)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_verified_download_and_cache(voice_builder, tmp_path, monkeypatch):
    data = b'verified voice bytes'
    expected = hashlib.sha256(data).hexdigest()
    calls = []
    monkeypatch.setattr(voice_builder.urllib.request, 'urlopen', lambda *a, **k: calls.append(1) or io.BytesIO(data))
    target = tmp_path / 'voice.onnx'
    voice_builder.fetch('https://example.invalid/voice', target, expected)
    voice_builder.fetch('https://example.invalid/voice', target, expected)
    assert target.read_bytes() == data and len(calls) == 1
    target.write_bytes(b'tampered')
    voice_builder.fetch('https://example.invalid/voice', target, expected)
    assert target.read_bytes() == data and len(calls) == 2


def test_checksum_failure_never_installs_download(voice_builder, tmp_path, monkeypatch):
    target = tmp_path / 'voice.onnx'
    target.write_bytes(b'old bytes')
    monkeypatch.setattr(voice_builder.urllib.request, 'urlopen', lambda *a, **k: io.BytesIO(b'wrong bytes'))
    with pytest.raises(RuntimeError, match='SHA-256 mismatch'):
        voice_builder.fetch('https://example.invalid/voice', target, '0' * 64)
    assert target.read_bytes() == b'old bytes'
    assert not target.with_suffix('.onnx.download').exists()
