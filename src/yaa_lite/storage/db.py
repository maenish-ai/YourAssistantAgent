from __future__ import annotations

import sqlite3
import threading
from pathlib import Path

from ..config import data_dir


class ChatDB:
    def __init__(self, path: Path | None = None):
        self.path = path or (data_dir() / "assistant.sqlite3")
        self._lock = threading.RLock()
        self._init()

    def _connect(self):
        return sqlite3.connect(self.path, timeout=5)

    def _init(self):
        with self._lock, self._connect() as con:
            con.execute("PRAGMA journal_mode=WAL")
            con.execute("PRAGMA synchronous=NORMAL")
            con.execute("CREATE TABLE IF NOT EXISTS messages (id INTEGER PRIMARY KEY AUTOINCREMENT, role TEXT NOT NULL, content TEXT NOT NULL, agent TEXT NOT NULL, created_at TEXT DEFAULT CURRENT_TIMESTAMP)")
            con.execute("CREATE TABLE IF NOT EXISTS activity (id INTEGER PRIMARY KEY AUTOINCREMENT, kind TEXT NOT NULL, detail TEXT NOT NULL, created_at TEXT DEFAULT CURRENT_TIMESTAMP)")

    def add_message(self, role: str, content: str, agent: str):
        with self._lock, self._connect() as con:
            con.execute("INSERT INTO messages(role,content,agent) VALUES(?,?,?)", (role, content, agent))

    def recent_messages(self, agent: str, limit: int = 30) -> list[dict]:
        with self._lock, self._connect() as con:
            rows = con.execute("SELECT role,content FROM messages WHERE agent=? ORDER BY id DESC LIMIT ?", (agent, limit)).fetchall()
        return [{"role": r, "content": c} for r, c in reversed(rows)]

    def add_activity(self, kind: str, detail: str):
        with self._lock, self._connect() as con:
            con.execute("INSERT INTO activity(kind,detail) VALUES(?,?)", (kind, detail))
