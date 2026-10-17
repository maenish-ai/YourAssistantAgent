from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def test_chatgpt_like_shell_has_agreed_primary_pages():
    app = (ROOT / "src" / "yaa_lite" / "ui" / "app.py").read_text(encoding="utf-8")
    for text in ("الرئيسية", "Home", "محادثة جديدة", "Chat", "الحالة", "Status", "Facebook", "المهام", "Tasks", "النسخ الاحتياطي", "Backup", "الإعدادات", "Settings"):
        assert text in app
    assert "sessions_frame" in app
    settings = (ROOT / "src" / "yaa_lite" / "ui" / "settings_view.py").read_text(encoding="utf-8")
    assert "Advanced" in settings


def test_ai_errors_are_logged_not_dumped_raw_into_chat():
    chat = (ROOT / "src" / "yaa_lite" / "ui" / "chat_window.py").read_text(encoding="utf-8")
    assert 'self.db.add_activity("ai_error"' in chat
    assert "technical details" in chat
    assert "Qwen3 could not complete" in chat


def test_runtime_has_two_safe_retries_and_diagnostics():
    runtime = (ROOT / "src" / "yaa_lite" / "ai" / "runtime.py").read_text(encoding="utf-8")
    assert '"local_ai.log"' in runtime
    assert "low-memory mode" in runtime
    assert "ultra-safe" in runtime
    assert "performance_mode" in runtime
    assert "Qwen prewarm completed" in runtime
