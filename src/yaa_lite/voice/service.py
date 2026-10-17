from __future__ import annotations

import audioop
import ctypes
import json
import os
import queue
import subprocess
import tempfile
import time
import wave
from pathlib import Path

from ..ai.runtime import bundle_root


class VoiceError(RuntimeError):
    pass


def _short_path(path: Path) -> str:
    """Best-effort Windows 8.3 path for native tools with Unicode path bugs."""
    text = str(path)
    if os.name != "nt":
        return text
    try:
        buf = ctypes.create_unicode_buffer(32768)
        n = ctypes.windll.kernel32.GetShortPathNameW(text, buf, len(buf))
        if n:
            return buf.value
    except Exception:
        pass
    return text


class VoiceService:
    """Offline push-to-talk voice pipeline for Windows.

    Input: microphone -> sounddevice/PortAudio -> WAV -> whisper.cpp.
    Output: Piper Arabic voice when bundled, with Windows SAPI as fallback.
    No cloud audio is used by this class.
    """

    SAMPLE_RATE = 16000
    CHANNELS = 1
    SAMPLE_WIDTH = 2
    BLOCK_FRAMES = 1600  # 100 ms at 16 kHz

    def __init__(self, settings):
        self.settings = settings
        if os.name != "nt":
            raise VoiceError("Local voice currently requires Windows.")
        if getattr(settings, "voice_backend", "local") != "local":
            raise VoiceError("Cloud voice is not configured. Select Local voice.")

    @staticmethod
    def _ps(script: str, timeout: int = 45) -> str:
        cp = subprocess.run(
            ["powershell.exe", "-NoProfile", "-NonInteractive", "-ExecutionPolicy", "Bypass", "-Command", script],
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=timeout,
            creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
        )
        if cp.returncode != 0:
            raise VoiceError((cp.stderr or cp.stdout or "Voice command failed").strip())
        return cp.stdout.strip()

    @staticmethod
    def _find_file(candidates: list[Path], recursive_root: Path | None = None, name: str = "") -> Path | None:
        for p in candidates:
            if p.exists():
                return p
        if recursive_root and recursive_root.exists() and name:
            try:
                return next(recursive_root.rglob(name))
            except StopIteration:
                pass
        return None

    def _whisper_binary(self) -> Path:
        root = bundle_root()
        runtime = root / "runtime"
        p = self._find_file(
            [runtime / "whisper" / "whisper-cli.exe", runtime / "whisper-cli.exe"],
            runtime,
            "whisper-cli.exe",
        )
        if not p:
            raise VoiceError("whisper.cpp is not installed in this build.")
        return p

    def _whisper_model(self) -> Path:
        root = bundle_root()
        candidates = [
            root / "models" / "voice" / "ggml-base.bin",
            root / "models" / "ggml-base.bin",
        ]
        p = self._find_file(candidates, root / "models", "ggml-base.bin")
        if not p:
            raise VoiceError("Whisper Arabic model is missing from this build.")
        return p

    def _piper_binary(self) -> Path | None:
        root = bundle_root() / "runtime"
        return self._find_file(
            [root / "piper" / "piper.exe", root / "piper.exe"],
            root,
            "piper.exe",
        )

    def _piper_model(self) -> Path | None:
        root = bundle_root() / "models"
        return self._find_file(
            [root / "voice" / "ar_JO-kareem-medium.onnx", root / "ar_JO-kareem-medium.onnx"],
            root,
            "ar_JO-kareem-medium.onnx",
        )

    def _record_wav(self, path: Path) -> None:
        try:
            import sounddevice as sd
        except Exception as exc:
            raise VoiceError(f"Microphone runtime is unavailable: {exc}") from exc

        start_timeout = 7.0
        max_duration = 18.0
        end_silence = 1.0
        calibration_blocks = 5
        blocks: list[bytes] = []
        noise_samples: list[int] = []
        speech_started = False
        silent_for = 0.0
        started_at = time.monotonic()

        try:
            with sd.RawInputStream(
                samplerate=self.SAMPLE_RATE,
                blocksize=self.BLOCK_FRAMES,
                dtype="int16",
                channels=self.CHANNELS,
            ) as stream:
                while True:
                    data, overflowed = stream.read(self.BLOCK_FRAMES)
                    raw = bytes(data)
                    if not raw:
                        continue
                    rms = int(audioop.rms(raw, self.SAMPLE_WIDTH))
                    if len(noise_samples) < calibration_blocks:
                        noise_samples.append(rms)
                        blocks.append(raw)
                        continue

                    baseline = max(80, int(sum(noise_samples) / max(1, len(noise_samples))))
                    threshold = max(220, min(2500, int(baseline * 2.6 + 90)))
                    block_seconds = self.BLOCK_FRAMES / self.SAMPLE_RATE

                    if rms >= threshold:
                        speech_started = True
                        silent_for = 0.0
                    elif speech_started:
                        silent_for += block_seconds

                    if speech_started:
                        blocks.append(raw)
                    elif time.monotonic() - started_at > start_timeout:
                        raise VoiceError("لم أسمع كلامًا واضحًا من الميكروفون. جرّب الاقتراب من الميكروفون ثم أعد المحاولة.")

                    elapsed = time.monotonic() - started_at
                    if speech_started and silent_for >= end_silence and len(blocks) >= 8:
                        break
                    if elapsed >= max_duration:
                        break
        except VoiceError:
            raise
        except Exception as exc:
            raise VoiceError(f"تعذر فتح الميكروفون: {exc}") from exc

        if not speech_started or not blocks:
            raise VoiceError("لم يتم التقاط صوت واضح.")

        with wave.open(str(path), "wb") as wf:
            wf.setnchannels(self.CHANNELS)
            wf.setsampwidth(self.SAMPLE_WIDTH)
            wf.setframerate(self.SAMPLE_RATE)
            wf.writeframes(b"".join(blocks))

    def listen_once(self) -> str:
        whisper = self._whisper_binary()
        model = self._whisper_model()
        lang = "ar" if getattr(self.settings, "interface_language", "ar") == "ar" else "en"
        threads = max(1, min(int(getattr(self.settings, "threads", 2) or 2), 4))

        with tempfile.TemporaryDirectory(prefix="yaa_voice_") as td:
            td_path = Path(td)
            wav = td_path / "input.wav"
            out_prefix = td_path / "transcript"
            self._record_wav(wav)

            cmd = [
                _short_path(whisper),
                "-m", _short_path(model),
                "-l", lang,
                "-t", str(threads),
                "-nt",
                "-np",
                "--output-txt",
                "--output-file", _short_path(out_prefix),
                _short_path(wav),
            ]
            cp = subprocess.run(
                cmd,
                capture_output=True,
                text=True,
                encoding="utf-8",
                errors="replace",
                timeout=75,
                creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
            )
            txt_file = out_prefix.with_suffix(".txt")
            text = ""
            if txt_file.exists():
                text = txt_file.read_text(encoding="utf-8", errors="replace").strip()
            if not text:
                text = (cp.stdout or "").strip()
            if cp.returncode != 0 and not text:
                raise VoiceError((cp.stderr or "Whisper transcription failed").strip())
            text = " ".join(text.split()).strip()
            if not text:
                raise VoiceError("سمعت الصوت لكن لم أستطع فهم الكلام. جرّب مرة ثانية بصوت أوضح.")
            return text

    def _speak_piper(self, text: str) -> bool:
        piper = self._piper_binary()
        model = self._piper_model()
        if not piper or not model:
            return False
        with tempfile.TemporaryDirectory(prefix="yaa_tts_") as td:
            wav = Path(td) / "reply.wav"
            cmd = [
                _short_path(piper),
                "--model", _short_path(model),
                "--output_file", _short_path(wav),
            ]
            cp = subprocess.run(
                cmd,
                input=text,
                capture_output=True,
                text=True,
                encoding="utf-8",
                errors="replace",
                timeout=90,
                cwd=str(piper.parent),
                creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
            )
            if cp.returncode != 0 or not wav.exists():
                return False
            try:
                import winsound
                winsound.PlaySound(str(wav), winsound.SND_FILENAME)
                return True
            except Exception:
                return False

    def _speak_sapi(self, text: str) -> None:
        rate_pct = max(50, min(int(getattr(self.settings, "voice_rate", 100)), 150))
        volume = max(0, min(int(getattr(self.settings, "voice_volume", 90)), 100))
        rate = round((rate_pct - 100) / 10)
        payload = json.dumps(text, ensure_ascii=False)
        script = rf'''
Add-Type -AssemblyName System.Speech
$s = New-Object System.Speech.Synthesis.SpeechSynthesizer
$s.Volume = {volume}
$s.Rate = {max(-10, min(rate, 10))}
$txt = ConvertFrom-Json @'
{payload}
'@
$s.Speak([string]$txt)
$s.Dispose()
'''
        self._ps(script, timeout=90)

    def speak(self, text: str) -> None:
        text = str(text or "").strip()
        if not text:
            return
        if self._speak_piper(text):
            return
        self._speak_sapi(text)
