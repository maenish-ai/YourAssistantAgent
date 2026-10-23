"""UI-release acceptance guards that run without a display or Groq credentials."""
import ast
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SOURCE = ROOT / 'src/yaa_lite/text_first_v300.py'


def _pure_helpers():
    tree = ast.parse(SOURCE.read_text(encoding='utf-8'))
    keep = {'is_single_facebook_link', 'normalize_listen_text', 'requires_local_tools'}
    nodes = [n for n in tree.body if isinstance(n, ast.FunctionDef) and n.name in keep]
    namespace = {'re': re}
    exec(compile(ast.Module(body=nodes, type_ignores=[]), str(SOURCE), 'exec'), namespace)
    return namespace


def test_single_facebook_url_asks_for_instruction():
    helper = _pure_helpers()['is_single_facebook_link']
    assert helper('https://www.facebook.com/profile.php?id=1234')
    assert helper('https://m.facebook.com/some.profile/')
    assert not helper('افتح https://www.facebook.com/profile.php?id=1234')
    assert not helper('https://example.com/profile.php')


def test_normal_chats_skip_tool_router_but_actions_do_not():
    helper = _pure_helpers()['requires_local_tools']
    assert not helper('مرحبا كيف حالك؟')
    assert not helper('اشرح لي نظرية النسبية ببساطة')
    assert helper('افتح جيت هاب')
    assert helper('افحص المهام')
    assert helper('انشر على فيسبوك')
    assert helper('Upload the repo')


def test_stt_joins_words_without_auto_send():
    helper = _pure_helpers()['normalize_listen_text']
    assert helper('مرحبا   كيفك\nاليوم') == 'مرحبا كيفك اليوم'


def test_text_first_no_tts_or_old_fullscreen_sweep():
    source = SOURCE.read_text(encoding='utf-8')
    launcher = (ROOT / 'launcher.py').read_text(encoding='utf-8')
    main = (ROOT / 'src/yaa_lite/main.py').read_text(encoding='utf-8')
    assert 'apply_text_first_v300()' in launcher
    assert 'def disable_voice_reply(' in source
    assert 'ChatWindow._maybe_speak_reply = disable_voice_reply' in source
    assert 'self.engine.reply(' in source
    assert 'history=[], ' not in source  # routing uses new prompt, not old persisted messages
    assert 'def _cloud_label_sweep' not in main
    assert 'after(700' not in main
    assert 'VoiceService' not in main


def test_security_review_and_bounded_request():
    source = SOURCE.read_text(encoding='utf-8')
    assert 'REQUEST_DEADLINE_MS = 50_000' in source
    assert 'pending_signature(pending)' in source
    assert 'clear_pending_action(self.session_id)' in source
    assert "is_click_approval = (text == 'نعم'" in source
    assert 'self.controller._v270_authorization' in source


def test_packaged_without_edge_tts_extra_dependencies():
    spec = (ROOT / 'build_app.spec').read_text(encoding='utf-8')
    workflow = (ROOT / '.github/workflows/build-windows.yml').read_text(encoding='utf-8')
    assert 'collect_all("edge_tts")' not in spec
    assert 'edge_tts' not in workflow
    assert 'YourAssistantAgent-Windows-Setup-v3.0-TextFirst' in workflow
