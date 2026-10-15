from yaa_lite.storage.db import ChatDB


def test_chat_sessions_and_titles(tmp_path):
    db = ChatDB(tmp_path / "db.sqlite3")
    sid = db.create_session("arabic")
    db.add_message("user", "كيف حالك", "arabic", sid)
    db.rename_session_from_first_message(sid, "كيف حالك اليوم")
    s = db.get_session(sid)
    assert s["title"].startswith("كيف حالك")
    assert db.recent_messages("arabic", session_id=sid)[0]["content"] == "كيف حالك"
