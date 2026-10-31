"""v2.8 regression tests — no actual microphone or network needed."""
from __future__ import annotations

import threading
import wave
from array import array
from dataclasses import dataclass
from pathlib import Path
from types import SimpleNamespace

import pytest

from yaa_lite.voice.capture_v280 import input_devices, choose_input, capture_wav, rms_int16
from yaa_lite.voice.cloud_service import CloudVoiceService, VoiceCancelled


class FakeStream:
    def __init__(self, sd, samplerate, blocksize, device, **kwargs):
        self.sd, self.rate, self.frames, self.device = sd, samplerate, blocksize, device
        self.sd.opened.append((samplerate, blocksize, device))
        self.cursor = 0
    def __enter__(self): return self
    def __exit__(self, *_): return False
    def read(self, n):
        amplitude = self.sd.pattern[min(self.cursor, len(self.sd.pattern)-1)]
        self.cursor += 1
        data = array('h', [amplitude] * n).tobytes()
        return data, False


class FakeSD:
    def __init__(self, pattern, rate=48000):
        self.pattern = pattern
        self.rate = rate
        self.default = SimpleNamespace(device=(3, 2))
        self.opened = []
    def query_hostapis(self): return [{'name': 'WASAPI'}]
    def query_devices(self):
        return [
            {'name': 'Speaker', 'max_input_channels': 0, 'hostapi': 0, 'default_samplerate': self.rate},
            {'name': 'USB Mic', 'max_input_channels': 1, 'hostapi': 0, 'default_samplerate': self.rate},
            {'name': 'Other Mic', 'max_input_channels': 2, 'hostapi': 0, 'default_samplerate': self.rate},
            {'name': 'Laptop Mic', 'max_input_channels': 1, 'hostapi': 0, 'default_samplerate': self.rate},
        ]
    def RawInputStream(self, **kwargs): return FakeStream(self, **kwargs)


def test_only_input_devices_visible_and_selected_by_stable_name():
    sd = FakeSD([0])
    devices = input_devices(sd)
    assert [d.index for d in devices] == [1, 2, 3]
    assert choose_input(SimpleNamespace(voice_input_device='auto'), sd).index == 3
    assert choose_input(SimpleNamespace(voice_input_device='USB Mic — WASAPI'), sd).index == 1
    with pytest.raises(RuntimeError, match='لم يعد متصلاً'):
        choose_input(SimpleNamespace(voice_input_device='Unplugged — WASAPI'), sd)


def test_48khz_device_writes_correct_wav_header_and_never_discards_early_speech(tmp_path):
    sd = FakeSD([0] * 5 + [430] * 35 + [0] * 60, rate=48000)
    path = tmp_path / 'audio.wav'
    levels=[]
    result=capture_wav(path, SimpleNamespace(voice_input_device='auto'), threading.Event(),
                       level_callback=levels.append, sd=sd)
    with wave.open(str(path),'rb') as wf:
        assert wf.getframerate() == 48000
        assert wf.getnchannels() == 1
        assert wf.getsampwidth() == 2
        assert wf.getnframes() > 48000
    assert result.peak_rms == 430
    assert max(levels) > 0.2
    assert sd.opened[0][2] == 3


def test_soft_microphone_will_be_sent_to_whisper_without_hard_gate(tmp_path):
    sd=FakeSD([45] * 130, rate=44100)
    report = capture_wav(tmp_path / 'quiet.wav', SimpleNamespace(voice_input_device='auto'),
                         threading.Event(), sd=sd)
    assert report.peak_rms == 45
    assert report.duration >= 5.9
    with wave.open(str(tmp_path / 'quiet.wav'), 'rb') as wf:
        assert wf.getframerate() == 44100


def test_zero_mic_signal_shows_actionable_error(tmp_path):
    sd=FakeSD([0] * 140)
    with pytest.raises(RuntimeError, match='إعداد|صوت كاف'):
        capture_wav(tmp_path/'no.wav', SimpleNamespace(voice_input_device='auto'),
                    threading.Event(), sd=sd)


def test_diagnostic_always_captures_four_seconds_locally(tmp_path):
    sd=FakeSD([0]*200)
    path=tmp_path/'diagnostic.wav'
    report=capture_wav(path, SimpleNamespace(voice_input_device='auto'),
                       threading.Event(), diagnostic_seconds=4, sd=sd)
    assert abs(report.duration-4)<0.1
    assert path.exists()


def test_cancel_closes_stream_without_leaving_files(tmp_path):
    sd=FakeSD([300]*200)
    stop=threading.Event();stop.set()
    path=tmp_path/'cancel.wav'
    with pytest.raises(VoiceCancelled):
        capture_wav(path, SimpleNamespace(voice_input_device='auto'), stop, sd=sd)
    assert not path.exists()


def test_cloud_service_uses_capture_v280(monkeypatch, tmp_path):
    from yaa_lite.voice import capture_v280
    values=[]
    def record(path, settings, event, callback, *, finish_event=None):
        values.append((path,settings,event,callback,finish_event))
    monkeypatch.setattr(capture_v280,'capture_wav',record)
    svc=CloudVoiceService(SimpleNamespace(voice_input_device='auto'))
    svc._record_wav(tmp_path/'input.wav')
    assert len(values)==1
    assert values[0][2] is svc.cancel_event
    assert values[0][4] is svc.finish_event


def test_launcher_loads_repair_last():
    bootstrap=(Path(__file__).resolve().parents[1]/'src/yaa_lite/bootstrap.py').read_text()
    assert bootstrap.index('apply_review_voice_v270()') < bootstrap.index('apply_repair_v280()')


def test_background_does_not_rearm_duplicate_backup_poll():
    import inspect
    from yaa_lite.repair_v280 import install_lightweight_background
    import yaa_lite.repair_v280 as repair
    source=inspect.getsource(repair.install_lightweight_background)
    assert '_poll_backup_sync' not in source
