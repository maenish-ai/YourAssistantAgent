from __future__ import annotations

from yaa_lite.cloud_voice_v240 import _is_facebook_status_request
from yaa_lite.voice.cloud_service import CloudVoiceService


def test_cloud_voice_defaults_are_accuracy_first_and_female():
    assert CloudVoiceService.STT_MODEL == "whisper-large-v3"
    assert CloudVoiceService.TTS_MODEL_AR == "canopylabs/orpheus-arabic-saudi"
    assert CloudVoiceService.TTS_VOICE_AR == "noura"


def test_tts_chunks_stay_under_orpheus_limit():
    text = "مرحبا، هذا اختبار للصوت العربي اللطيف. " * 40
    chunks = CloudVoiceService._split_tts_text(text)
    assert chunks
    assert all(1 <= len(chunk) <= CloudVoiceService.TTS_CHUNK_LIMIT for chunk in chunks)


def test_facebook_status_routes_directly():
    assert _is_facebook_status_request("افحص حالة الفيس بوك عندي")
    assert _is_facebook_status_request("تأكد إذا فيسبوك متصل")
    assert _is_facebook_status_request("check facebook connection")
    assert not _is_facebook_status_request("افتح فيسبوك")
    assert not _is_facebook_status_request("انشر آخر إعلان على فيسبوك")
