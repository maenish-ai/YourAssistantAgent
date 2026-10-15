from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def test_chatgpt_like_shell_keeps_secondary_pages_in_sidebar():
    app = (ROOT / "src" / "yaa_lite" / "ui" / "app.py").read_text(encoding="utf-8")
    assert "محادثة جديدة" in app
    assert "المحادثة" in app
    assert "النشاط" in app
    assert "الإعدادات" in app
    assert "متقدم" in app
    assert "sessions_frame" in app


def test_ai_errors_are_not_dumped_raw_into_chat():
    chat = (ROOT / "src" / "yaa_lite" / "ui" / "chat_window.py").read_text(encoding="utf-8")
    assert "التفاصيل موجودة في النشاط" in chat
    assert 'self.db.add_activity("ai_error"' in chat


def test_runtime_writes_diagnostics_and_has_low_memory_retry():
    runtime = (ROOT / "src" / "yaa_lite" / "ai" / "runtime.py").read_text(encoding="utf-8")
    assert '"local_ai.log"' in runtime
    assert "safe_mode" in runtime
    assert "batch = 16 if safe_mode else 32" in runtime
