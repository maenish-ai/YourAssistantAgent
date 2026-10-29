"""Tests for review-before-execution and cloud voice provider selection."""
from __future__ import annotations
from datetime import datetime, timedelta, timezone
from pathlib import Path
import json
import threading
import time
import pytest

from yaa_lite.review_voice_v270 import (
    pending_signature, pending_is_fresh, permitted_mutation,
    _LOCAL_APPROVAL, _APPROVAL_TTL_SECONDS,
)
from yaa_lite.voice import provider_v270 as vp


def _pending(**change):
    d = dict(tool_name='approve_facebook_campaign', arguments={'plan': {'groups': 3}},
             summary='Share a verified post to three groups',
             created_at=datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M:%S'))
    d.update(change)
    return d


def test_rejects_old_pending_and_unknown_sensitive_type():
    old = _pending(created_at=(datetime.now(timezone.utc) - timedelta(seconds=_APPROVAL_TTL_SECONDS + 10)).strftime('%Y-%m-%d %H:%M:%S'))
    assert not pending_is_fresh(old)
    assert not pending_is_fresh(_pending(tool_name='save_facebook_share_rule'))
    assert pending_is_fresh(_pending())
    assert not pending_is_fresh(_pending(created_at='corrupt'))


def test_signature_binds_exact_operation_and_summary():
    a = _pending()
    assert pending_signature(a) == pending_signature(dict(a))
    assert pending_signature(a) != pending_signature(_pending(summary='Different groups'))
    assert pending_signature(a) != pending_signature(_pending(arguments={'plan': {'groups': 4}}))


def test_sensitive_execution_denied_without_local_click_token():
    _LOCAL_APPROVAL.details = None
    assert permitted_mutation('facebook_status', {})
    assert permitted_mutation('open_facebook_login', {})
    assert not permitted_mutation('approve_facebook_campaign', {'plan': {'groups': 3}})
    assert not permitted_mutation('run_facebook_rule_now', {'rule_id': 8})
    assert not permitted_mutation('save_facebook_share_rule', {})
    assert not permitted_mutation('new_unsafe_tool', {})
    _LOCAL_APPROVAL.details = dict(tool='approve_facebook_campaign',
                                  arguments=json.dumps({'plan': {'groups': 3}}, ensure_ascii=False,
                                                       separators=(',', ':'), sort_keys=True),
                                  deadline=time.monotonic() + 30)
    try:
        assert permitted_mutation('approve_facebook_campaign', {'plan': {'groups': 3}})
        assert not permitted_mutation('approve_facebook_campaign', {'plan': {'groups': 4}})
        assert not permitted_mutation('run_facebook_rule_now', {'rule_id': 8})
    finally:
        _LOCAL_APPROVAL.details = None


def test_voice_preference_is_only_allowlisted_and_does_not_store_secrets(tmp_path, monkeypatch):
    monkeypatch.setattr(vp, '_preference_path', lambda: tmp_path / 'voice.json')
    assert vp.get_voice_preference() == 'noura'
    vp.set_voice_preference('sana')
    assert vp.get_voice_preference() == 'sana'
    assert 'sana' in (tmp_path / 'voice.json').read_text(encoding='utf-8')
    with pytest.raises(ValueError):
        vp.set_voice_preference('evil_command')
    assert vp.get_voice_preference() == 'sana'
    (tmp_path / 'voice.json').write_text('{broken', encoding='utf-8')
    assert vp.get_voice_preference() == 'noura'


def test_sensitive_tokens_are_redacted_before_any_tts():
    sample = 'مفتاحك gsk_supersecret12345678 وبعده github_pat_supersecret98765432'
    out = vp.redact_sensitive_text(sample)
    assert 'gsk_' not in out and 'github_pat_' not in out
    assert 'بيانات سرية' in out


def test_sana_never_claims_it_is_groq_and_is_windows_only(monkeypatch):
    if __import__('os').name != 'nt':
        with pytest.raises(RuntimeError, match='Windows'):
            vp.speak_with_provider('sana', 'مرحبا', threading.Event())
    with pytest.raises(ValueError):
        vp.speak_with_provider('noura', 'مرحبا', threading.Event())
