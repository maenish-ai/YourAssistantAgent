"""v2.6 regression tests: never replay, guess page photos, or require payments."""
from __future__ import annotations

import threading
import pytest

from yaa_lite.stability_v260 import (
    TurnCancelled, _CANCEL, _check_cancel, explicit_github_intent, explicit_git_status_intent,
    facebook_page_ambiguous, open_github_desktop, should_discard_pending,
)
from yaa_lite.voice.cloud_service import CloudVoiceService, VoiceError


def test_ambiguous_page_task_is_not_sent_to_automatic_browser_navigation():
    assert facebook_page_ambiguous('سويلي على صفحتي معن حنون الستلايت قبل الإعلان')
    assert facebook_page_ambiguous('ثبتلي منشور على صفحتي قبل الإعلان')
    assert not facebook_page_ambiguous('افتح الفيسبوك')
    assert not facebook_page_ambiguous('افحص حالة فيسبوك')


def test_old_campaign_pending_is_not_carried_into_unrelated_new_command():
    assert should_discard_pending('افتح الفيسبوك')
    assert should_discard_pending('سويلي على صفحتي الإعلان')
    assert not should_discard_pending('غير الساعة إلى 8')
    assert not should_discard_pending('نعم')
    assert not should_discard_pending('إلغاء')


def test_explicit_local_github_desktop_launch_intent():
    assert explicit_github_intent('افتح جيت هاب ديسكتوب')
    assert explicit_github_intent('افتح github desktop')
    assert not explicit_github_intent('اعمل push للمستودع')
    assert not explicit_github_intent('افتح الصور على فيسبوك')
    assert explicit_git_status_intent('افحص حالة GitHub')
    assert not explicit_git_status_intent('انشر إعلان')


def test_request_cancel_event_stops_tools_between_turns():
    event = threading.Event()
    _CANCEL.event = event
    _check_cancel()
    event.set()
    with pytest.raises(TurnCancelled):
        _check_cancel()
    _CANCEL.event = None


def test_no_auto_installer_or_github_authentication_on_nonwindows():
    import os
    if os.name != 'nt':
        ok, text = open_github_desktop()
        assert ok is False and 'Windows' in text


def test_cloud_tts_reports_failure_instead_of_silent_loop(monkeypatch):
    voice = CloudVoiceService(object())
    monkeypatch.setattr(voice, '_speak_cloud_arabic', lambda text: False)
    monkeypatch.setattr(voice, '_sapi_fallback', lambda text: False)
    with pytest.raises(VoiceError, match='نورا'):
        voice.speak('مرحبا')
    monkeypatch.setattr(voice, '_speak_cloud_arabic', lambda text: True)
    assert voice.speak('مرحبا') == 'noura'
