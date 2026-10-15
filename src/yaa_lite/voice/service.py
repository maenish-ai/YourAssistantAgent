from __future__ import annotations

import json
import os
import subprocess


class VoiceError(RuntimeError):
    pass


class VoiceService:
    """Lazy Windows voice helper using built-in System.Speech.

    No cloud audio is sent by this class. Speech recognition quality and
    available voices depend on language packs installed in Windows.
    """

    def __init__(self, settings):
        self.settings = settings
        if os.name != "nt":
            raise VoiceError("Local voice currently requires Windows.")
        if getattr(settings, "voice_backend", "local") != "local":
            raise VoiceError("Cloud voice is not configured. Select Local or install a cloud voice skill.")

    @staticmethod
    def _ps(script: str, timeout: int = 45) -> str:
        cp = subprocess.run(
            ["powershell.exe", "-NoProfile", "-NonInteractive", "-ExecutionPolicy", "Bypass", "-Command", script],
            capture_output=True, text=True, timeout=timeout, creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
        )
        if cp.returncode != 0:
            raise VoiceError((cp.stderr or cp.stdout or "Voice command failed").strip())
        return cp.stdout.strip()

    def listen_once(self) -> str:
        culture = "ar-JO" if getattr(self.settings, "interface_language", "ar") == "ar" else "en-US"
        # Recognize one utterance from the default Windows microphone. If that
        # culture is unavailable, fall back to the system recognizer.
        script = rf'''
Add-Type -AssemblyName System.Speech
try {{
  $ci = New-Object System.Globalization.CultureInfo('{culture}')
  $r = New-Object System.Speech.Recognition.SpeechRecognitionEngine($ci)
}} catch {{
  $r = New-Object System.Speech.Recognition.SpeechRecognitionEngine
}}
$r.SetInputToDefaultAudioDevice()
$r.LoadGrammar((New-Object System.Speech.Recognition.DictationGrammar))
$r.InitialSilenceTimeout = [TimeSpan]::FromSeconds(8)
$r.BabbleTimeout = [TimeSpan]::FromSeconds(4)
$r.EndSilenceTimeout = [TimeSpan]::FromMilliseconds(800)
$x = $r.Recognize([TimeSpan]::FromSeconds(20))
if ($null -ne $x) {{ [Console]::OutputEncoding=[Text.Encoding]::UTF8; Write-Output $x.Text }}
$r.Dispose()
'''
        return self._ps(script, timeout=30).strip()

    def speak(self, text: str) -> None:
        if not text:
            return
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
