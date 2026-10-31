from pathlib import Path
from yaa_lite.config import Settings
from yaa_lite.security.manager import SecurityManager
from yaa_lite.storage.db import ChatDB

ROOT=Path(__file__).resolve().parents[1]


def test_security_password_recovery_and_windows_session(tmp_path):
    sec=SecurityManager(tmp_path)
    recovery=sec.setup("1234","windows_session")
    assert recovery.startswith("YAA-")
    blob=sec.encrypt(b"secret",b"test")
    sec2=SecurityManager(tmp_path)
    assert not sec2.unlocked
    assert sec2.unlock_with_password("1234")
    assert sec2.decrypt(blob,b"test")==b"secret"
    sec3=SecurityManager(tmp_path)
    assert sec3.unlock_with_recovery(recovery)
    assert sec3.decrypt(blob,b"test")==b"secret"


def test_db_session_controls_memory_and_global_search(tmp_path):
    db=ChatDB(tmp_path/"db.sqlite3")
    sid=db.create_session("hammer", title="خلدة")
    db.update_session(sid,pinned=True,category="Facebook",is_private=True,memory_enabled=False)
    row=db.get_session(sid)
    assert row["pinned"]==1 and row["category"]=="Facebook" and row["is_private"]==1 and row["memory_enabled"]==0
    db.add_memory_item("preference","جروبات خلدة",sid)
    assert any(r["type"]=="memory" for r in db.global_search("خلدة"))


def test_browser_extension_command_channel_is_packaged():
    manifest=(ROOT/"browser_extension"/"manifest.json").read_text(encoding="utf-8")
    bg=(ROOT/"browser_extension"/"background.js").read_text(encoding="utf-8")
    spec=(ROOT/"build_app.spec").read_text(encoding="utf-8")
    assert '"scripting"' in manifest and '"<all_urls>"' in manifest
    assert "/next-command" in bg and "/command-result" in bg
    assert '"browser_extension"' in spec


def test_first_run_and_single_language_ui_are_present():
    s=Settings()
    assert not s.first_run_complete
    assert s.interface_language in {"ar","en"}
    setup=(ROOT/"src"/"yaa_lite"/"ui"/"setup_wizard.py").read_text(encoding="utf-8")
    assert "Recovery key" in setup or "مفتاح الاسترداد" in setup

def test_portable_backup_can_be_opened_with_recovery_key(tmp_path, monkeypatch):
    import yaa_lite.backup.crypto_backup as cb
    data = tmp_path / "data"; config = tmp_path / "config"
    data.mkdir(); config.mkdir()
    (data / "sample.txt").write_text("hello", encoding="utf-8")
    sec = SecurityManager(config)
    recovery = sec.setup("pass123", "every_launch")
    monkeypatch.setattr(cb, "data_dir", lambda: data)
    monkeypatch.setattr(cb, "config_dir", lambda: config)
    backup = tmp_path / "portable.yaa-backup"
    cb.create_backup_with_security(backup, sec)
    assert cb.backup_header(backup)["key_envelope"]["recovery_salt"]
    (data / "sample.txt").write_text("changed", encoding="utf-8")
    cb.restore_backup_with_secret(backup, recovery, use_recovery=True)
    assert (data / "sample.txt").read_text(encoding="utf-8") == "hello"
