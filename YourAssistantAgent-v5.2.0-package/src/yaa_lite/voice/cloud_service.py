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
    STT_MODEL_LIVE = "whisper-large-v3-turbo"
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

    START_TIMEOUT = 6.0
    MAX_DURATION = 16.0
    END_SILENCE = 0.6
    CALIBRATION_BLOCKS = 6
    PREROLL_BLOCKS = 7

    def __init__(self, settings):
        self.settings = settings
        self.cancel_event = threading.Event()
        self.finish_event = threading.Event()

    def finish(self):
        """Finish the current recording and transcribe its tail; do not cancel it."""
        self.finish_event.set()

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

    def _record_wav(self, path: Path, level_callback: LevelCallback | None = None):
        from .capture_v280 import capture_wav
        try:
            return capture_wav(path, self.settings, self.cancel_event, level_callback,finish_event=self.finish_event)
        except VoiceCancelled:
            raise
        except Exception as exc:
            raise VoiceError(str(exc)) from exc

    def listen_once(self, level_callback: LevelCallback | None = None, mode: str = "dictation") -> str:
        with tempfile.TemporaryDirectory(prefix="yaa_cloud_voice_") as td:
            wav = Path(td) / "input.wav"
            report=self._record_wav(wav, level_callback=level_callback)
            if report and (report.duration<.2 or report.peak_rms<35):raise VoiceError('ما سمعت كلام واضح؛ لم أضف نصاً من الصمت.')
            if self.cancel_event.is_set():raise VoiceCancelled('Voice listening cancelled.')
            return self.transcribe_file(wav,mode=mode)

    def transcribe_file(self,path: Path,*,mode='dictation',mime='audio/wav'):
        key = get_groq_api_key(required=True)
        try:
            with Path(path).open("rb") as f:
                response = requests.post(
                    self.STT_URL,
                    headers={
                        "Authorization": f"Bearer {key}",
                        "User-Agent": "YourAssistantAgent/2.5",
                    },
                    files={"file": (Path(path).name, f, mime)},
                    data={
                        "model": self.STT_MODEL_LIVE if mode == "live" else self.STT_MODEL,
                        "language": "ar",
                        "prompt": self.STT_PROMPT_AR,
                        "response_format": "verbose_json",
                        "temperature": "0",
                    },
                    timeout=(4, 12) if mode == "live" else (5, 35),
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
            payload=response.json()
            text = str(payload.get('text') or '')
            segments=payload.get('segments')
            if isinstance(segments,list) and segments:
                supported=any(isinstance(segment,dict) and float(segment.get('no_speech_prob',0))<.85 and float(segment.get('avg_logprob',0))>-1.5 for segment in segments)
                if not supported:raise VoiceError('ما سمعت كلام واضح؛ أعد الجملة دون ضجيج.')
        except VoiceError:raise
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
        for chunk in chunks:
            if self.cancel_event.is_set():
                raise VoiceCancelled("Voice playback cancelled.")
            try:
                response = requests.post(
                    self.TTS_URL,
                    headers={
                        "Authorization": f"Bearer {key}",
                        "Content-Type": "application/json",
                        "User-Agent": "YourAssistantAgent/2.5",
                    },
                    json={
                        "model": self.TTS_MODEL_AR,
                        "voice": self.TTS_VOICE_AR,
                        "input": chunk,
                        "response_format": "wav",
                    },
                    timeout=(4, 12),
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

    def _sapi_fallback(self, text: str) -> bool:
        if os.name != "nt":
            return False
        payload = json.dumps(str(text or ""), ensure_ascii=False)
        # Prefer a female Windows voice if one exists. This fallback downloads
        # nothing and is only used when cloud TTS is unavailable.
        script = rf"""
Add-Type -AssemblyName System.Speech
$s = New-Object System.Speech.Synthesis.SpeechSynthesizer
$voices = @($s.GetInstalledVoices() | ForEach-Object {{ $_.VoiceInfo }})
$female = $voices | Where-Object {{ $_.Gender -eq 'Female' -and $_.Culture.Name -like 'ar-*' }} | Select-Object -First 1
if (-not $female) {{ $female = $voices | Where-Object {{ $_.Culture.Name -like 'ar-*' }} | Select-Object -First 1 }}
if (-not $female) {{ exit 4 }}
$s.SelectVoice($female.Name)
$s.Volume = 90
$s.Rate = -1
$txt = ConvertFrom-Json @'
{payload}
'@
$s.Speak([string]$txt)
$s.Dispose()
"""
        proc = subprocess.Popen(
            ["powershell.exe", "-NoProfile", "-NonInteractive", "-ExecutionPolicy", "Bypass", "-Command", script],
            stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
            creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
        )
        deadline = time.monotonic() + 12
        while proc.poll() is None:
            if self.cancel_event.is_set() or time.monotonic() >= deadline:
                proc.terminate()
                try:
                    proc.wait(timeout=1)
                except subprocess.TimeoutExpired:
                    proc.kill()
                return False
            time.sleep(0.05)
        return proc.returncode == 0

    def speak(self, text: str) -> str:
        text = str(text or "").strip()
        if not text:
            return "none"
        try:
            if self._speak_cloud_arabic(text):
                return "noura"
        except VoiceCancelled:
            raise
        except Exception:
            pass
        if self.cancel_event.is_set():
            raise VoiceCancelled("Voice was stopped.")
        if self._sapi_fallback(text):
            return "windows"
        raise VoiceError("صوت نورا السحابي غير متاح الآن، وما لقيت صوت عربي احتياطي على ويندوز. راجع حدود Groq المجانية أو الاتصال بالإنترنت.")
