"""Two opt-in Arabic female voice providers; no model files or account tokens saved.

Noura is the official Groq Orpheus voice. Sana is an *experimental*, unofficial
third-party Edge TTS client; selecting it sends spoken text to Microsoft and may
stop working without warning. It is NOT uploaded to, or hosted by, Groq.
"""
from __future__ import annotations

import asyncio
import json
import os
import re
import subprocess
import tempfile
import threading
import time
from pathlib import Path

from platformdirs import user_config_dir

VOICE_CHOICES = frozenset({'noura', 'sana'})
PUBLIC_PREVIEW_TEXT = 'أهلين! كيفك اليوم؟ أنا مساعدتك الشخصية، جاهزة أساعدك بكل محبة واهتمام.'
_SANA_VOICE = 'ar-JO-SanaNeural'
_SECRET_PATTERNS = (
    re.compile(r'\b(?:gsk_|ghp_|gho_|github_pat_|sk-|xoxb-|xoxp-)[A-Za-z0-9_-]{8,}', re.I),
    re.compile(r'\bBearer\s+[A-Za-z0-9._~+/=-]{12,}', re.I),
    re.compile(r'(?i)(?:api[_ -]?key|secret|access[_ -]?token)\s*[:=]\s*[^\s,;]{8,}'),
)


def redact_sensitive_text(text: str) -> str:
    result = str(text or '')
    for pattern in _SECRET_PATTERNS:
        result = pattern.sub('[بيانات سرية مخفية]', result)
    return result


def _preference_path() -> Path:
    return Path(user_config_dir('YourAssistantAgent', 'YourAssistantAgent')) / 'voice_preference.json'


def get_voice_preference() -> str:
    try:
        data = json.loads(_preference_path().read_text(encoding='utf-8'))
        choice = str(data.get('provider') or 'noura')
        return choice if choice in VOICE_CHOICES else 'noura'
    except (OSError, ValueError, TypeError):
        return 'noura'


def set_voice_preference(provider: str) -> None:
    if provider not in VOICE_CHOICES:
        raise ValueError('Unknown voice provider')
    path = _preference_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    # This file has no API keys and only stores the choice of narrator.
    with tempfile.NamedTemporaryFile('w', encoding='utf-8', prefix='yaa_voice_', suffix='.json',
                                     dir=str(path.parent), delete=False) as f:
        temp_name = f.name
        json.dump({'provider': provider}, f)
    try:
        os.replace(temp_name, path)
    finally:
        if os.path.exists(temp_name):
            os.unlink(temp_name)


def _play_mp3_windows(mp3: Path, cancel_event: threading.Event) -> None:
    """Cancellable native .NET playback; no bundled MP3 player or downloaded EXE."""
    if os.name != 'nt':
        raise RuntimeError('Sana playback is supported on Windows only')
    script = r'''param([string]$AudioPath)
$ErrorActionPreference = 'Stop'
Add-Type -AssemblyName PresentationCore
$p = New-Object System.Windows.Media.MediaPlayer
try {
    $p.Open([uri]::new($AudioPath))
    $limit = (Get-Date).AddSeconds(8)
    while ((-not $p.NaturalDuration.HasTimeSpan) -and (Get-Date) -lt $limit) {
        Start-Sleep -Milliseconds 120
    }
    if (-not $p.NaturalDuration.HasTimeSpan) { throw 'MP3 could not be loaded' }
    $duration = [Math]::Max(400, [Math]::Min(30000, $p.NaturalDuration.TimeSpan.TotalMilliseconds + 200))
    $p.Play()
    Start-Sleep -Milliseconds ([int]$duration)
} finally { $p.Stop(); $p.Close() }
'''
    with tempfile.TemporaryDirectory(prefix='yaa_sana_play_') as td:
        script_path = Path(td) / 'play.ps1'
        script_path.write_text(script, encoding='utf-8-sig')
        proc = subprocess.Popen(
            ['powershell.exe', '-NoProfile', '-NonInteractive', '-STA', '-ExecutionPolicy', 'Bypass',
             '-File', str(script_path), str(mp3)],
            stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL, stderr=subprocess.PIPE,
            creationflags=getattr(subprocess, 'CREATE_NO_WINDOW', 0),
        )
        deadline = time.monotonic() + 36
        try:
            while proc.poll() is None:
                if cancel_event.is_set():
                    raise RuntimeError('تم إلغاء تشغيل الصوت')
                if time.monotonic() > deadline:
                    raise TimeoutError('انتهت مهلة تشغيل Sana')
                time.sleep(.08)
            if proc.returncode != 0:
                reason = (proc.stderr.read() or b'')[-300:].decode('utf-8', errors='replace')
                raise RuntimeError('Windows could not play Sana MP3: ' + reason[:120])
        finally:
            if proc.poll() is None:
                proc.terminate()
                try:
                    proc.wait(timeout=1.0)
                except subprocess.TimeoutExpired:
                    proc.kill()


def speak_with_provider(provider: str, text: str, cancel_event: threading.Event) -> str:
    """Sana only here. Noura stays on the official CloudVoiceService endpoint."""
    if provider != 'sana':
        raise ValueError('Use CloudVoiceService for Noura')
    if cancel_event.is_set():
        raise RuntimeError('تم إلغاء الصوت')
    if os.name != 'nt':
        raise RuntimeError('Sana voice requires Windows playback')
    # Keep spoken responses concise, both for privacy and response latency.
    clean_text = ' '.join(redact_sensitive_text(text).split()).strip()[:190]
    if not clean_text:
        return 'none'
    try:
        import edge_tts  # available only when bundled by the selected Windows build
    except ImportError as exc:
        raise RuntimeError('مكتبة edge-tts غير موجودة في هذا الإصدار') from exc
    with tempfile.TemporaryDirectory(prefix='yaa_sana_voice_') as td:
        mp3 = Path(td) / 'speech.mp3'
        async def synth():
            client = edge_tts.Communicate(clean_text, voice=_SANA_VOICE,
                                          rate='-8%', pitch='+0Hz',
                                          connect_timeout=5, receive_timeout=8)
            await client.save(str(mp3))
        try:
            asyncio.run(asyncio.wait_for(synth(), timeout=17))
        except Exception as exc:
            raise RuntimeError('خدمة Sana التجريبية لم تستجب؛ جرّب Noura الرسمية.') from exc
        if cancel_event.is_set():
            raise RuntimeError('تم إلغاء الصوت')
        if not mp3.is_file() or mp3.stat().st_size < 100:
            raise RuntimeError('لم يصل صوت صالح من Sana')
        _play_mp3_windows(mp3, cancel_event)
    return 'sana'
