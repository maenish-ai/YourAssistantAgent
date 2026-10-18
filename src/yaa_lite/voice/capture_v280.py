"""Low-overhead Windows microphone capture with explicit input-device selection.

Records at the INPUT DEVICE'S NATIVE sampling rate. WAV headers preserve that
rate; Groq Whisper accepts WAV without a local model or resampling dependency.
No microphone is opened until the user explicitly starts voice/diagnostics.
"""
from __future__ import annotations

import math
import statistics
import threading
import wave
from array import array
from dataclasses import dataclass
from pathlib import Path
from typing import Callable


@dataclass(frozen=True)
class InputDevice:
    index: int
    label: str
    samplerate: int


@dataclass(frozen=True)
class CaptureReport:
    device_label: str
    samplerate: int
    duration: float
    peak_rms: int
    started: bool


def _sounddevice():
    try:
        import sounddevice as sd
        return sd
    except Exception as exc:
        raise RuntimeError('مكتبة الميكروفون غير متاحة. راجع إعدادات الصوت: ' + str(exc)) from exc


def input_devices(sd=None) -> list[InputDevice]:
    sd = sd or _sounddevice()
    hosts = sd.query_hostapis()
    out: list[InputDevice] = []
    for index, info in enumerate(sd.query_devices()):
        if int(info.get('max_input_channels') or 0) < 1:
            continue
        name = str(info.get('name') or 'Microphone')
        host_id = int(info.get('hostapi', 0))
        host = str(hosts[host_id].get('name') or '') if 0 <= host_id < len(hosts) else ''
        label = f'{name} — {host}'
        native_rate = int(round(float(info.get('default_samplerate') or 48000)))
        out.append(InputDevice(index, label, native_rate if 8000 <= native_rate <= 192000 else 48000))
    return out


def choose_input(settings, sd=None) -> InputDevice:
    sd = sd or _sounddevice()
    devices = input_devices(sd)
    if not devices:
        raise RuntimeError('ويندوز ما أظهر أي ميكروفون إدخال. تحقق من أذونات المايك وتوصيله.')
    wanted = str(getattr(settings, 'voice_input_device', 'auto') or 'auto')
    if wanted != 'auto':
        for device in devices:
            if device.label == wanted:
                return device
        raise RuntimeError('الميكروفون المحفوظ لم يعد متصلاً. افتح «إعداد الميكروفون» واختر جهازًا آخر.')
    try:
        default_idx = int(sd.default.device[0])
    except (ValueError, IndexError, TypeError, AttributeError):
        default_idx = -1
    return next((dev for dev in devices if dev.index == default_idx), devices[0])


def rms_int16(raw: bytes) -> int:
    samples = array('h')
    samples.frombytes(raw)
    if not samples:
        return 0
    return math.isqrt(sum(int(s) * int(s) for s in samples) // len(samples))


def capture_wav(
    path: Path,
    settings,
    cancel_event: threading.Event,
    level_callback: Callable[[float], None] | None = None,
    *,
    diagnostic_seconds: float | None = None,
    sd=None,
) -> CaptureReport:
    """Capture an input WAV using bounded memory and soft speech detection.

    Unlike the legacy capture, no first-second samples are discarded, and quiet
    but non-zero speech is sent to Whisper rather than being rejected locally.
    Diagnostic recordings have a fixed length and are never sent to the cloud.
    """
    sd = sd or _sounddevice()
    device = choose_input(settings, sd)
    rate = device.samplerate
    frames_per_block = max(160, int(rate * .05))
    seconds_per_block = frames_per_block / rate
    max_seconds = max(1.0, min(5.0, float(diagnostic_seconds))) if diagnostic_seconds else 16.0
    max_blocks = math.ceil(max_seconds / seconds_per_block)
    start_blocks = math.ceil(6.0 / seconds_per_block)
    min_speech_blocks = math.ceil(1.2 / seconds_per_block)
    end_silence_blocks = math.ceil(.85 / seconds_per_block)
    captured: list[bytes] = []
    levels: list[int] = []
    speech_started = False
    silence_count = 0
    first_speech_block = 0
    peak = 0
    try:
        with sd.RawInputStream(samplerate=rate, blocksize=frames_per_block,
                               dtype='int16', channels=1, device=device.index) as stream:
            for block_index in range(max_blocks):
                if cancel_event.is_set():
                    from .cloud_service import VoiceCancelled
                    raise VoiceCancelled('تم إيقاف تسجيل الصوت.')
                raw, _overflow = stream.read(frames_per_block)
                chunk = bytes(raw)
                if not chunk:
                    continue
                captured.append(chunk)
                rms = rms_int16(chunk)
                peak = max(peak, rms)
                if len(levels) < 6:
                    levels.append(rms)
                ambient = max(18, int(statistics.median(levels)))
                threshold = max(40, min(1500, int(ambient * 1.5 + 10)))
                if level_callback:
                    try:
                        level_callback(min(1.0, rms / max(250.0, threshold * 3)))
                    except Exception:
                        pass  # A closed UI must not abort the audio stream.
                if diagnostic_seconds:
                    continue
                if rms >= threshold or (block_index < 6 and rms >= 110):
                    if not speech_started:
                        first_speech_block = block_index
                    speech_started = True
                    silence_count = 0
                elif speech_started:
                    silence_count += 1
                if speech_started and block_index - first_speech_block >= min_speech_blocks and silence_count >= end_silence_blocks:
                    break
                if not speech_started and block_index + 1 >= start_blocks:
                    # Let Whisper analyze a non-silent quiet signal. The former
                    # local hard gate incorrectly rejected soft microphones.
                    if peak >= 35:
                        break
                    raise RuntimeError(f'لا يصل صوت كافٍ من «{device.label}» (مستوى {peak}). افتح اختبار الميكروفون واختر مدخلًا آخر.')
    except Exception as exc:
        from .cloud_service import VoiceCancelled
        if isinstance(exc, VoiceCancelled):
            raise
        if isinstance(exc, RuntimeError) and ('الميكروفون' in str(exc) or 'صوت كاف' in str(exc)):
            raise
        raise RuntimeError(f'تعذر تسجيل الصوت من «{device.label}»: {exc}') from exc
    if not captured:
        raise RuntimeError(f'لم يصل صوت من «{device.label}».')
    # Never write a misleading 16 kHz WAV header for a device sampling at 48 kHz.
    with wave.open(str(path), 'wb') as audio:
        audio.setnchannels(1)
        audio.setsampwidth(2)
        audio.setframerate(rate)
        audio.writeframes(b''.join(captured))
    return CaptureReport(device.label, rate, len(captured) * seconds_per_block, peak, speech_started)
