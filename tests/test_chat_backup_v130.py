from pathlib import Path

from your_assistant_agent.cloud_backup import decrypt_blob, encrypt_blob, generate_recovery_key
from your_assistant_agent.db import Database


def test_encrypted_backup_roundtrip():
    key = generate_recovery_key()
    payload = b"private chat and settings"
    encrypted = encrypt_blob(payload, key)
    assert encrypted != payload
    assert decrypt_blob(encrypted, key) == payload


def test_chat_history_roundtrip(tmp_path):
    db = Database(tmp_path / "agent.db")
    db.add_chat_message("user", "انشر على جروبات خلدة", ["photo.jpg"], {"x": 1})
    db.add_chat_message("assistant", "فهمت عليك")
    rows = db.list_chat_messages(limit=10)
    assert len(rows) == 2
    assert rows[0]["role"] == "user"
    assert "خلدة" in rows[0]["text"]
    assert "photo.jpg" in rows[0]["attachments_json"]
    assert "USER:" in db.chat_context_text(limit=10)
    db.clear_chat_messages()
    assert db.list_chat_messages(limit=10) == []


def test_v130_defaults_exist(tmp_path):
    db = Database(tmp_path / "agent.db")
    assert db.get_setting("auto_discover_groups") is True
    assert db.get_setting("cloud_backup_keep_versions") == 7
    assert db.get_setting("agent_ai_provider") == "local"
