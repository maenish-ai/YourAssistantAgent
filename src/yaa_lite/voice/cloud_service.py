from __future__ import annotations

import json
import math
import os
import subprocess
import tempfile
import threading
import time
import wave
from collections import deque
from pathlib import Path
from typing import Callable

import requests

from ..ai.runtime import get_groq_api_key


class VoiceError(RuntimeError):
    pass


class VoiceCancelled(VoiceError):
    pass


LevelCallback = Callable[[float], None]


class CloudVoiceService:
    """Cloud-first Arabic voice for Your Assistant Agent.

    - Microphone capture is local and lightweight.
    - STT: Groq Whisper Large V3 with Arabic forced for accuracy.
    - TTS: Groq Orpheus Arabic Saudi, female voice ``noura``.
    - No local speech model is downloaded or packaged.
    - Windows SAPI is used only as a zero-download fallback when cloud TTS is
      unavailable or a free-tier limit is reached.

    The service is cancellation-aware and has hard timeouts so a stalled audio
    request cannot freeze the desktop UI.
    """

    SAMPLE_RATE = 16000
    CHANNELS = 1
    SAMPLE_WIDTH = 2
    BLOCK_FRAMES = 800  # 50 ms; responsive waveform and silence detection

    STT_URL = "https://api.groq.com/openai/v1/audio/transcriptions"
    STT_MODEL = "whisper-large-v3"
    STT_PROMPT_AR = (
        "المتحدث عربي باللهجة الأردنية/الشامية. اكتب الكلام كما قيل بالعربية. "
        "مصطلحات متوقعة: فيسبوك، جروبات، إعلان، منشور، آخر منشور، اعتمد، "
        "افحص الاتصال، GroqCloud، GPT-OSS، مساعد، مهمة، جدول، بكرة، اليوم."
    )

    TTS_URL = "https://api.groq.com/openai/v1/audio/speech"
    TTS_MODEL_AR = "canopylabs/orpheus-arabic-saudi"
    TTS_VOICE_AR = "noura"
    TTS_SPEED = 0.92
    TTS_CHUNK_LIMIT = 190  # Orpheus Arabic input limit is 200 chars.

    START_TIMEOUT = 10.0
    MAX_DURATION = 28.0
    END_SILENCE = 0.85
    CALIBRATION_BLOCKS = 6
    PREROLL_BLOCKS = 7

    def __init__(self, settings):
        self.settings = settings
        self.cancel_event = threading.Event()

    def cancel(self) -> None:
        self.cancel_event.set()
        if os.name == "nt":
            try:
                import winsound
                winsound.PlaySound(None, 0)
            except Exception:
                pass

    def reset_cancel(self) -> None:
        self.cancel_event.clear()

    @staticmethod
    def _rms(raw: bytes) -> int:
        if not raw:
            return 0
        try:
            samples = memoryview(raw).cast("h")
            if not samples:
                return 0
            total = 0
            for sample in samples:
                total += int(sample) * int(sample)
            return int(math.sqrt(total / len(samples)))
        except Exception:
            return 0

    def _record_wav(self, path: Path, level_callback: LevelCallback | None = None) -> None:
        try:
            import sounddevice as sd
        except Exception as exc:
            raise VoiceError(f"Microphone runtime is unavailable: {exc}") from exc

        self.reset_cancel()
        started_at = time.monotonic()
        noise_samples: list[int] = []
        pre_roll: deque[bytes] = deque(maxlen=self.PREROLL_BLOCKS)
        captured: list[bytes] = []
        speech_started = False
        silent_for = 0.0
        threshold = 220

        try:
            with sd.RawInputStream(
                samplerate=self.SAMPLE_RATE,
                blocksize=self.BLOCK_FRAMES,
                dtype="int16",
                channels=self.CHANNELS,
            ) as stream:
                while True:
                    if self.cancel_event.is_set():
                        raise VoiceCancelled("Voice listening cancelled.")

                    data, overflowed = stream.read(self.BLOCK_FRAMES)
                    raw = bytes(data)
                    if not raw:
                        continue
                    rms = self._rms(raw)

                    if len(noise_samples) < self.CALIBRATION_BLOCKS:
                        noise_samples.append(rms)
                        pre_roll.append(raw)
                        if level_callback:
                            level_callback(min(1.0, rms / 1200.0))
                        continue

                    baseline = max(55, int(sum(noise_samples) / len(noise_samples)))
                    threshold = max(180, min(2200, int(baseline * 2.15 + 70)))
                    level = min(1.0, max(0.015, rms / max(420.0, threshold * 2.8)))
                    if overflowed:
                        level = max(level, 0.35)
                    if level_callback:
                        level_callback(level)

                    block_seconds = self.BLOCK_FRAMES / self.SAMPLE_RATE
                    if rms >= threshold:
                        if not speech_started:
                            captured.extend(pre_roll)
                            pre_roll.clear()
                        speech_started = True
                        silent_for = 0.0
                        captured.append(raw)
                    elif speech_started:
                        captured.append(raw)
                        silent_for += block_seconds
                    else:
                        pre_roll.append(raw)

                    elapsed = time.monotonic() - started_at
                    if not speech_started and elapsed >= self.START_TIMEOUT:
                        raise VoiceError("ما سمعت كلام واضح. قرّب شوي من الميكروفون وجرب مرة ثانية.")
                    if speech_started and silent_for >= self.END_SILENCE and len(captured) >= 10:
                        break
                    if elapsed >= self.MAX_DURATION:
                        break
        except (VoiceError, VoiceCancelled):
            raise
        except Exception as exc:
            raise VoiceError(f"تعذر فتح الميكروفون: {exc}") from exc

        if not speech_started or not captured:
            raise VoiceError("ما قدرت ألتقط صوت واضح من الميكروفون.")

        with wave.open(str(path), "wb") as wf:
            wf.setnchannels(self.CHANNELS)
            wf.setsampwidth(self.SAMPLE_WIDTH)
            wf.setframerate(self.SAMPLE_RATE)
            wf.writeframes(b"".join(captured))

    def listen_once(self, level_callback: LevelCallback | None = None) -> str:
        key = get_groq_api_key(required=True)
        with tempfile.TemporaryDirectory(prefix="yaa_cloud_voice_") as td:
            wav = Path(td) / "input.wav"
            self._record_wav(wav, level_callback=level_callback)
            if self.cancel_event.is_set():
                raise VoiceCancelled("Voice listening cancelled.")
            try:
                with wav.open("rb") as f:
                    response = requests.post(
                        self.STT_URL,
                        headers={
                            "Authorization": f"Bearer {key}",
                            "User-Agent": "YourAssistantAgent/2.4",
                        },
                        files={"file": ("input.wav", f, "audio/wav")},
                        data={
                            "model": self.STT_MODEL,
                            "language": "ar",
                            "prompt": self.STT_PROMPT_AR,
                            "response_format": "json",
                            "temperature": "0",
                        },
                        timeout=(8, 45),
                    )
            except requests.RequestException as exc:
                raise VoiceError(f"تعذر الاتصال بخدمة فهم الصوت: {exc}") from exc

            if response.status_code == 401:
                raise VoiceError("GroqCloud رفض مفتاح API. راجع GROQ_API_KEY.")
            if response.status_code == 429:
                raise VoiceError("وصلت للحد المجاني للصوت مؤقتًا. جرّب بعد قليل.")
            if not response.ok:
                raise VoiceError(f"فشل فهم الصوت (HTTP {response.status_code}).")

            try:
                text = str(response.json().get("text") or "")
            except Exception as exc:
                raise VoiceError("وصل رد غير صالح من خدمة فهم الصوت.") from exc

            text = " ".join(text.split()).strip()
            if not text:
                raise VoiceError("سمعت الصوت، لكن ما قدرت أفهم الكلام. جرّب مرة ثانية.")
            return text

    @classmethod
    def _split_tts_text(cls, text: str) -> list[str]:
        text = " ".join(str(text or "").split()).strip()
        if not text:
            return []
        chunks: list[str] = []
        remaining = text
        separators = (". ", "؟ ", "! ", "، ", "; ", ": ")
        while len(remaining) > cls.TTS_CHUNK_LIMIT:
            cut = -1
            probe = remaining[: cls.TTS_CHUNK_LIMIT + 1]
            for sep in separators:
                idx = probe.rfind(sep)
                if idx > cut:
                    cut = idx + len(sep.rstrip())
            if cut < 70:
                cut = probe.rfind(" ")
            if cut < 40:
                cut = cls.TTS_CHUNK_LIMIT
            chunk = remaining[:cut].strip()
            if chunk:
                chunks.append(chunk)
            remaining = remaining[cut:].strip()
        if remaining:
            chunks.append(remaining)
        return chunks

    def _play_wav_cancelable(self, path: Path) -> None:
        if os.name != "nt":
            raise VoiceError("Cloud voice playback currently requires Windows.")
        try:
            import winsound
            with wave.open(str(path), "rb") as wf:
                duration = wf.getnframes() / max(1, wf.getframerate())
            winsound.PlaySound(str(path), winsound.SND_FILENAME | winsound.SND_ASYNC)
            end = time.monotonic() + min(max(duration + 0.25, 0.5), 60.0)
            while time.monotonic() < end:
                if self.cancel_event.is_set():
                    winsound.PlaySound(None, 0)
                    raise VoiceCancelled("Voice playback cancelled.")
                time.sleep(0.05)
        except VoiceCancelled:
            raise
        except Exception as exc:
            raise VoiceError(f"تعذر تشغيل الرد الصوتي: {exc}") from exc

    def _speak_cloud_arabic(self, text: str) -> bool:
        key = get_groq_api_key(required=True)
        chunks = self._split_tts_text(text)
        if not chunks:
            return True
        self.reset_cancel()
        for chunk in chunks:
            if self.cancel_event.is_set():
                raise VoiceCancelled("Voice playback cancelled.")
            try:
                response = requests.post(
                    self.TTS_URL,
                    headers={
                        "Authorization": f"Bearer {key}",
                        "Content-Type": "application/json",
                        "User-Agent": "YourAssistantAgent/2.4",
                    },
                    json={
                        "model": self.TTS_MODEL_AR,
                        "voice": self.TTS_VOICE_AR,
                        "input": chunk,
                        "response_format": "wav",
                        "speed": self.TTS_SPEED,
                    },
                    timeout=(8, 40),
                )
            except requests.RequestException:
                return False
            if response.status_code in {401, 403, 404, 429} or not response.ok:
                return False
            with tempfile.TemporaryDirectory(prefix="yaa_orpheus_") as td:
                wav = Path(td) / "reply.wav"
                wav.write_bytes(response.content)
                try:
                    self._play_wav_cancelable(wav)
                except VoiceCancelled:
                    raise
                except VoiceError:
                    return False
        return True

    @staticmethod
    def _sapi_fallback(text: str) -> None:
        if os.name != "nt":
            return
        payload = json.dumps(str(text or ""), ensure_ascii=False)
        # Prefer a female Windows voice if one exists. This fallback downloads
        # nothing and is only used when cloud TTS is unavailable.
        script = rf"""
Add-Type -AssemblyName System.Speech
$s = New-Object System.Speech.Synthesis.SpeechSynthesizer
$voices = @($s.GetInstalledVoices() | ForEach-Object {{ $_.VoiceInfo }})
$female = $voices | Where-Object {{ $_.Gender -eq 'Female' }} | Select-Object -First 1
if ($female) {{ $s.SelectVoice($female.Name) }}
$s.Volume = 90
$s.Rate = -1
$txt = ConvertFrom-Json @'
{payload}
'@
$s.Speak([string]$txt)
$s.Dispose()
"""
        subprocess.run(
            ["powershell.exe", "-NoProfile", "-NonInteractive", "-ExecutionPolicy", "Bypass", "-Command", script],
            capture_output=True,
            text=True,
            timeout=45,
            creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
        )

    def speak(self, text: str) -> None:
        text = str(text or "").strip()
        if not text:
            return
        try:
            if self._speak_cloud_arabic(text):
                return
        except VoiceCancelled:
            raise
        except Exception:
            pass
        if not self.cancel_event.is_set():
            self._sapi_fallback(text)
