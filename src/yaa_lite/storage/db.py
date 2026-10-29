from __future__ import annotations

import json
import sqlite3
import threading
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any

from ..config import data_dir


class ChatDB:
    """Single lightweight SQLite store for chat, activity and Smart Agent state.

    The schema is migrated in place so users upgrading from v1.5 keep their
    conversation history. WAL + short transactions keep the Tk UI responsive.
    """

    def __init__(self, path: Path | None = None):
        self.path = path or (data_dir() / "assistant.sqlite3")
        self._lock = threading.RLock()
        self._init()

    def _connect(self):
        con = sqlite3.connect(self.path, timeout=5)
        con.row_factory = sqlite3.Row
        return con

    @staticmethod
    def _columns(con: sqlite3.Connection, table: str) -> set[str]:
        return {str(r[1]) for r in con.execute(f"PRAGMA table_info({table})").fetchall()}

    def _init(self):
        with self._lock, self._connect() as con:
            con.execute("PRAGMA journal_mode=WAL")
            con.execute("PRAGMA synchronous=NORMAL")
            con.execute("PRAGMA foreign_keys=ON")
            con.execute(
                "CREATE TABLE IF NOT EXISTS sessions ("
                "id INTEGER PRIMARY KEY AUTOINCREMENT, title TEXT NOT NULL, agent TEXT NOT NULL, "
                "created_at TEXT DEFAULT CURRENT_TIMESTAMP, updated_at TEXT DEFAULT CURRENT_TIMESTAMP)"
            )
            # v2 conversation organization/privacy fields are added in-place.
            session_cols = self._columns(con, "sessions")
            for col, spec in {
                "pinned": "INTEGER NOT NULL DEFAULT 0",
                "archived": "INTEGER NOT NULL DEFAULT 0",
                "category": "TEXT NOT NULL DEFAULT ''",
                "is_private": "INTEGER NOT NULL DEFAULT 0",
                "memory_enabled": "INTEGER NOT NULL DEFAULT 1",
            }.items():
                if col not in session_cols:
                    con.execute(f"ALTER TABLE sessions ADD COLUMN {col} {spec}")
            con.execute(
                "CREATE TABLE IF NOT EXISTS messages ("
                "id INTEGER PRIMARY KEY AUTOINCREMENT, role TEXT NOT NULL, content TEXT NOT NULL, "
                "agent TEXT NOT NULL, session_id INTEGER, created_at TEXT DEFAULT CURRENT_TIMESTAMP)"
            )
            if "session_id" not in self._columns(con, "messages"):
                con.execute("ALTER TABLE messages ADD COLUMN session_id INTEGER")
            con.execute(
                "CREATE TABLE IF NOT EXISTS activity ("
                "id INTEGER PRIMARY KEY AUTOINCREMENT, kind TEXT NOT NULL, detail TEXT NOT NULL, "
                "created_at TEXT DEFAULT CURRENT_TIMESTAMP)"
            )
            con.execute(
                "CREATE TABLE IF NOT EXISTS facebook_groups ("
                "id INTEGER PRIMARY KEY AUTOINCREMENT, name TEXT NOT NULL, url TEXT NOT NULL UNIQUE, "
                "tags TEXT NOT NULL DEFAULT '', enabled INTEGER NOT NULL DEFAULT 1, "
                "discovered_at TEXT DEFAULT CURRENT_TIMESTAMP)"
            )
            con.execute(
                "CREATE TABLE IF NOT EXISTS smart_rules ("
                "id INTEGER PRIMARY KEY AUTOINCREMENT, name TEXT NOT NULL, command_text TEXT NOT NULL, "
                "source_page_url TEXT NOT NULL, weekdays TEXT NOT NULL DEFAULT '[]', run_time TEXT NOT NULL, "
                "run_once_at TEXT NOT NULL DEFAULT '', post_mode TEXT NOT NULL DEFAULT 'fixed', "
                "post_offset INTEGER NOT NULL DEFAULT 0, group_keyword TEXT NOT NULL DEFAULT '', "
                "max_groups INTEGER NOT NULL DEFAULT 100, interval_seconds INTEGER NOT NULL DEFAULT 60, "
                "no_repeat_days INTEGER NOT NULL DEFAULT 14, share_mode TEXT NOT NULL DEFAULT 'native_share', "
                "next_run_at TEXT, enabled INTEGER NOT NULL DEFAULT 1, created_at TEXT DEFAULT CURRENT_TIMESTAMP)"
            )
            rule_cols = self._columns(con, "smart_rules")
            for col, spec in {
                "post_count": "INTEGER NOT NULL DEFAULT 1",
                "post_urls": "TEXT NOT NULL DEFAULT '[]'",
                "selected_groups": "TEXT NOT NULL DEFAULT '[]'",
                "approval_snapshot": "INTEGER NOT NULL DEFAULT 0",
            }.items():
                if col not in rule_cols:
                    con.execute(f"ALTER TABLE smart_rules ADD COLUMN {col} {spec}")
            con.execute(
                "CREATE TABLE IF NOT EXISTS share_history ("
                "id INTEGER PRIMARY KEY AUTOINCREMENT, rule_id INTEGER, group_id INTEGER NOT NULL, "
                "post_url TEXT NOT NULL, status TEXT NOT NULL, detail TEXT NOT NULL DEFAULT '', "
                "created_at TEXT DEFAULT CURRENT_TIMESTAMP)"
            )
            con.execute(
                "CREATE TABLE IF NOT EXISTS pending_actions ("
                "session_id INTEGER PRIMARY KEY, tool_name TEXT NOT NULL, arguments_json TEXT NOT NULL, "
                "summary TEXT NOT NULL, created_at TEXT DEFAULT CURRENT_TIMESTAMP)"
            )
            con.execute(
                "CREATE TABLE IF NOT EXISTS memory_items ("
                "id INTEGER PRIMARY KEY AUTOINCREMENT, kind TEXT NOT NULL, content TEXT NOT NULL, "
                "source_session_id INTEGER, enabled INTEGER NOT NULL DEFAULT 1, "
                "created_at TEXT DEFAULT CURRENT_TIMESTAMP, updated_at TEXT DEFAULT CURRENT_TIMESTAMP)"
            )
            con.execute(
                "CREATE TABLE IF NOT EXISTS task_events ("
                "id INTEGER PRIMARY KEY AUTOINCREMENT, rule_id INTEGER, event TEXT NOT NULL, detail TEXT NOT NULL DEFAULT '', "
                "created_at TEXT DEFAULT CURRENT_TIMESTAMP)"
            )
            con.execute("CREATE INDEX IF NOT EXISTS idx_messages_session ON messages(session_id, id)")
            con.execute("CREATE INDEX IF NOT EXISTS idx_rules_due ON smart_rules(enabled, next_run_at)")
            con.execute("CREATE INDEX IF NOT EXISTS idx_share_lookup ON share_history(group_id, post_url, created_at)")
            con.execute("CREATE INDEX IF NOT EXISTS idx_sessions_sidebar ON sessions(archived,pinned,updated_at)")
            con.execute("CREATE INDEX IF NOT EXISTS idx_memory_enabled ON memory_items(enabled,updated_at)")

    # ---------------- Chat sessions ----------------
    def create_session(self, agent: str, title: str = "محادثة جديدة", category: str = "") -> int:
        with self._lock, self._connect() as con:
            cur = con.execute("INSERT INTO sessions(title,agent,category) VALUES(?,?,?)", (title[:120], agent, category[:60]))
            return int(cur.lastrowid)

    def ensure_session(self, agent: str) -> int:
        with self._lock, self._connect() as con:
            row = con.execute("SELECT id FROM sessions WHERE agent=? ORDER BY updated_at DESC, id DESC LIMIT 1", (agent,)).fetchone()
            if row:
                return int(row["id"])
        return self.create_session(agent)

    def list_sessions(self, limit: int = 50, include_archived: bool = False) -> list[dict]:
        with self._lock, self._connect() as con:
            if include_archived:
                rows = con.execute(
                    "SELECT * FROM sessions ORDER BY pinned DESC, updated_at DESC, id DESC LIMIT ?",
                    (max(1, int(limit)),),
                ).fetchall()
            else:
                rows = con.execute(
                    "SELECT * FROM sessions WHERE archived=0 ORDER BY pinned DESC, updated_at DESC, id DESC LIMIT ?",
                    (max(1, int(limit)),),
                ).fetchall()
        return [dict(r) for r in rows]

    def get_session(self, session_id: int) -> dict | None:
        with self._lock, self._connect() as con:
            row = con.execute("SELECT * FROM sessions WHERE id=?", (int(session_id),)).fetchone()
        return dict(row) if row else None

    def rename_session_from_first_message(self, session_id: int, text: str) -> None:
        title = " ".join((text or "").strip().split())[:48] or "محادثة جديدة"
        with self._lock, self._connect() as con:
            row = con.execute("SELECT title FROM sessions WHERE id=?", (int(session_id),)).fetchone()
            if row and str(row["title"]) in {"محادثة جديدة", "New chat"}:
                con.execute("UPDATE sessions SET title=?, updated_at=CURRENT_TIMESTAMP WHERE id=?", (title, int(session_id)))

    def update_session(self, session_id: int, *, title: str | None = None, pinned: bool | None = None,
                       archived: bool | None = None, category: str | None = None,
                       is_private: bool | None = None, memory_enabled: bool | None = None) -> None:
        fields, values = [], []
        for name, value in (("title", title), ("pinned", None if pinned is None else int(pinned)),
                            ("archived", None if archived is None else int(archived)),
                            ("category", category), ("is_private", None if is_private is None else int(is_private)),
                            ("memory_enabled", None if memory_enabled is None else int(memory_enabled))):
            if value is not None:
                fields.append(f"{name}=?")
                values.append(value)
        if not fields:
            return
        values.append(int(session_id))
        with self._lock, self._connect() as con:
            con.execute(f"UPDATE sessions SET {', '.join(fields)}, updated_at=CURRENT_TIMESTAMP WHERE id=?", values)

    def delete_session(self, session_id: int) -> None:
        with self._lock, self._connect() as con:
            con.execute("DELETE FROM messages WHERE session_id=?", (int(session_id),))
            con.execute("DELETE FROM pending_actions WHERE session_id=?", (int(session_id),))
            con.execute("DELETE FROM sessions WHERE id=?", (int(session_id),))

    def search_sessions(self, query: str, limit: int = 50) -> list[dict]:
        q = f"%{query.strip()}%"
        with self._lock, self._connect() as con:
            rows = con.execute(
                "SELECT DISTINCT s.* FROM sessions s LEFT JOIN messages m ON m.session_id=s.id "
                "WHERE s.archived=0 AND (s.title LIKE ? OR m.content LIKE ?) "
                "ORDER BY s.pinned DESC,s.updated_at DESC LIMIT ?",
                (q, q, max(1, int(limit))),
            ).fetchall()
        return [dict(r) for r in rows]

    def touch_session(self, session_id: int) -> None:
        with self._lock, self._connect() as con:
            con.execute("UPDATE sessions SET updated_at=CURRENT_TIMESTAMP WHERE id=?", (int(session_id),))

    def add_message(self, role: str, content: str, agent: str, session_id: int | None = None):
        with self._lock, self._connect() as con:
            con.execute(
                "INSERT INTO messages(role,content,agent,session_id) VALUES(?,?,?,?)",
                (role, content, agent, session_id),
            )
            if session_id:
                con.execute("UPDATE sessions SET updated_at=CURRENT_TIMESTAMP WHERE id=?", (int(session_id),))

    def recent_messages(self, agent: str, limit: int = 30, session_id: int | None = None) -> list[dict]:
        with self._lock, self._connect() as con:
            if session_id:
                rows = con.execute(
                    "SELECT role,content FROM messages WHERE session_id=? ORDER BY id DESC LIMIT ?",
                    (int(session_id), limit),
                ).fetchall()
            else:
                rows = con.execute(
                    "SELECT role,content FROM messages WHERE agent=? ORDER BY id DESC LIMIT ?",
                    (agent, limit),
                ).fetchall()
        return [{"role": r["role"], "content": r["content"]} for r in reversed(rows)]

    def clear_messages(self, agent: str | None = None, session_id: int | None = None) -> None:
        with self._lock, self._connect() as con:
            if session_id:
                con.execute("DELETE FROM messages WHERE session_id=?", (int(session_id),))
            elif agent:
                con.execute("DELETE FROM messages WHERE agent=?", (agent,))
            else:
                con.execute("DELETE FROM messages")

    # ---------------- Activity ----------------
    def add_activity(self, kind: str, detail: str):
        with self._lock, self._connect() as con:
            con.execute("INSERT INTO activity(kind,detail) VALUES(?,?)", (kind, (detail or "")[:8000]))

    def recent_activity(self, limit: int = 200) -> list[dict]:
        with self._lock, self._connect() as con:
            rows = con.execute(
                "SELECT id,created_at,kind,detail FROM activity ORDER BY id DESC LIMIT ?", (limit,)
            ).fetchall()
        return [dict(row) for row in rows]

    def clear_activity(self) -> None:
        with self._lock, self._connect() as con:
            con.execute("DELETE FROM activity")

    # ---------------- Pending agent actions ----------------
    def set_pending_action(self, session_id: int, tool_name: str, arguments: dict, summary: str) -> None:
        with self._lock, self._connect() as con:
            con.execute(
                "INSERT INTO pending_actions(session_id,tool_name,arguments_json,summary) VALUES(?,?,?,?) "
                "ON CONFLICT(session_id) DO UPDATE SET tool_name=excluded.tool_name, arguments_json=excluded.arguments_json, "
                "summary=excluded.summary, created_at=CURRENT_TIMESTAMP",
                (int(session_id), tool_name, json.dumps(arguments, ensure_ascii=False), summary),
            )

    def get_pending_action(self, session_id: int) -> dict | None:
        with self._lock, self._connect() as con:
            row = con.execute("SELECT * FROM pending_actions WHERE session_id=?", (int(session_id),)).fetchone()
        if not row:
            return None
        data = dict(row)
        try:
            data["arguments"] = json.loads(data.pop("arguments_json"))
        except Exception:
            data["arguments"] = {}
        return data

    def clear_pending_action(self, session_id: int) -> None:
        with self._lock, self._connect() as con:
            con.execute("DELETE FROM pending_actions WHERE session_id=?", (int(session_id),))

    # ---------------- Facebook groups ----------------
    def upsert_groups(self, groups: list[dict]) -> int:
        count = 0
        with self._lock, self._connect() as con:
            for g in groups:
                name = str(g.get("name") or "").strip()
                url = str(g.get("url") or "").strip()
                if not name or not url:
                    continue
                con.execute(
                    "INSERT INTO facebook_groups(name,url,tags,enabled) VALUES(?,?,?,1) "
                    "ON CONFLICT(url) DO UPDATE SET name=excluded.name, tags=excluded.tags, enabled=1, discovered_at=CURRENT_TIMESTAMP",
                    (name, url, str(g.get("tags") or "")),
                )
                count += 1
        return count

    @staticmethod
    def _norm(value: str) -> str:
        import re
        import unicodedata
        text = unicodedata.normalize("NFKC", value or "")
        text = re.sub(r"[\u0610-\u061A\u064B-\u065F\u0670\u06D6-\u06ED]", "", text).replace("ـ", "")
        text = text.translate(str.maketrans({"أ": "ا", "إ": "ا", "آ": "ا", "ٱ": "ا", "ى": "ي", "ؤ": "و", "ئ": "ي"}))
        return " ".join(text.split()).casefold()

    def list_groups(self, keyword: str = "", limit: int = 500, enabled_only: bool = True) -> list[dict]:
        with self._lock, self._connect() as con:
            if enabled_only:
                rows = con.execute("SELECT * FROM facebook_groups WHERE enabled=1 ORDER BY name LIMIT ?", (max(1, int(limit)),)).fetchall()
            else:
                rows = con.execute("SELECT * FROM facebook_groups ORDER BY name LIMIT ?", (max(1, int(limit)),)).fetchall()
        result = [dict(r) for r in rows]
        if keyword:
            n = self._norm(keyword)
            result = [g for g in result if n in self._norm(f"{g['name']} {g.get('tags','')}")]
        return result

    def count_groups(self, keyword: str = "") -> int:
        return len(self.list_groups(keyword=keyword, limit=5000))

    # ---------------- Smart rules ----------------
    def add_rule(self, plan: Any) -> int:
        weekdays = list(getattr(plan, "weekdays", []) or [])
        run_once_at = str(getattr(plan, "run_once_at", "") or "")
        if run_once_at:
            next_run = run_once_at
        else:
            from ..agent.legacy_smart import calculate_next_run
            next_run = calculate_next_run(weekdays, str(getattr(plan, "run_time", "20:00")))
        with self._lock, self._connect() as con:
            cur = con.execute(
                "INSERT INTO smart_rules(name,command_text,source_page_url,weekdays,run_time,run_once_at,post_mode,post_offset,"
                "group_keyword,max_groups,interval_seconds,no_repeat_days,share_mode,next_run_at,post_count,post_urls,selected_groups,approval_snapshot,enabled) "
                "VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,1)",
                (
                    str(plan.name), str(plan.command_text), str(plan.source_page_url), json.dumps(weekdays),
                    str(plan.run_time), run_once_at, str(plan.post_mode), int(plan.post_offset),
                    str(plan.group_keyword), int(plan.max_groups), int(plan.interval_seconds), int(plan.no_repeat_days),
                    str(plan.share_mode), next_run, max(1, min(4, int(getattr(plan, "post_count", 1)))),
                    json.dumps(getattr(plan, "post_urls", []) or [], ensure_ascii=False),
                    json.dumps(getattr(plan, "selected_groups", []) or [], ensure_ascii=False),
                    int(bool(getattr(plan, "approval_snapshot", False))),
                ),
            )
            return int(cur.lastrowid)

    def list_rules(self, limit: int = 100) -> list[dict]:
        with self._lock, self._connect() as con:
            rows = con.execute("SELECT * FROM smart_rules ORDER BY id DESC LIMIT ?", (max(1, int(limit)),)).fetchall()
        out = []
        for r in rows:
            d = dict(r)
            try:
                d["weekdays"] = json.loads(d.get("weekdays") or "[]")
            except Exception:
                d["weekdays"] = []
            for key in ("post_urls", "selected_groups"):
                try:
                    d[key] = json.loads(d.get(key) or "[]")
                except (ValueError, TypeError):
                    d[key] = []
            out.append(d)
        return out

    def get_rule(self, rule_id: int) -> dict | None:
        with self._lock, self._connect() as con:
            r = con.execute("SELECT * FROM smart_rules WHERE id=?", (int(rule_id),)).fetchone()
        if not r:
            return None
        d = dict(r)
        try:
            d["weekdays"] = json.loads(d.get("weekdays") or "[]")
        except Exception:
            d["weekdays"] = []
        for key in ("post_urls", "selected_groups"):
            try:
                d[key] = json.loads(d.get(key) or "[]")
            except (ValueError, TypeError):
                d[key] = []
        return d

    def due_rules(self, now_iso: str | None = None) -> list[dict]:
        now_iso = now_iso or datetime.now().replace(microsecond=0).isoformat()
        with self._lock, self._connect() as con:
            rows = con.execute(
                "SELECT * FROM smart_rules WHERE enabled=1 AND next_run_at IS NOT NULL AND next_run_at<=? ORDER BY next_run_at,id",
                (now_iso,),
            ).fetchall()
        return [self.get_rule(int(r["id"])) for r in rows if r]

    def advance_rule(self, rule_id: int) -> None:
        rule = self.get_rule(rule_id)
        if not rule:
            return
        if rule.get("run_once_at"):
            with self._lock, self._connect() as con:
                con.execute("UPDATE smart_rules SET enabled=0,next_run_at=NULL WHERE id=?", (int(rule_id),))
            return
        from ..agent.legacy_smart import calculate_next_run
        # Move the reference one second beyond now to avoid reselecting the same slot.
        next_run = calculate_next_run(rule.get("weekdays") or [], rule.get("run_time") or "20:00", datetime.now() + timedelta(seconds=1))
        with self._lock, self._connect() as con:
            con.execute("UPDATE smart_rules SET next_run_at=? WHERE id=?", (next_run, int(rule_id)))

    def set_rule_enabled(self, rule_id: int, enabled: bool) -> None:
        with self._lock, self._connect() as con:
            con.execute("UPDATE smart_rules SET enabled=? WHERE id=?", (1 if enabled else 0, int(rule_id)))

    def delete_rule(self, rule_id: int) -> None:
        with self._lock, self._connect() as con:
            con.execute("DELETE FROM smart_rules WHERE id=?", (int(rule_id),))

    def add_task_event(self, rule_id: int | None, event: str, detail: str = "") -> None:
        with self._lock, self._connect() as con:
            con.execute("INSERT INTO task_events(rule_id,event,detail) VALUES(?,?,?)", (rule_id, event, detail[:4000]))

    def add_memory_item(self, kind: str, content: str, source_session_id: int | None = None) -> int:
        with self._lock, self._connect() as con:
            cur = con.execute("INSERT INTO memory_items(kind,content,source_session_id) VALUES(?,?,?)",
                              (kind[:40], content[:8000], source_session_id))
            return int(cur.lastrowid)

    def list_memory_items(self, limit: int = 200, enabled_only: bool = True) -> list[dict]:
        with self._lock, self._connect() as con:
            sql = "SELECT * FROM memory_items" + (" WHERE enabled=1" if enabled_only else "") + " ORDER BY updated_at DESC,id DESC LIMIT ?"
            rows = con.execute(sql, (max(1, int(limit)),)).fetchall()
        return [dict(r) for r in rows]

    def set_memory_enabled(self, memory_id: int, enabled: bool) -> None:
        with self._lock, self._connect() as con:
            con.execute("UPDATE memory_items SET enabled=?,updated_at=CURRENT_TIMESTAMP WHERE id=?", (int(enabled), int(memory_id)))

    def delete_memory_item(self, memory_id: int) -> None:
        with self._lock, self._connect() as con:
            con.execute("DELETE FROM memory_items WHERE id=?", (int(memory_id),))

    def global_search(self, query: str, limit: int = 50) -> list[dict]:
        term = query.strip()
        if not term:
            return []
        q = f"%{term}%"
        results: list[dict] = []
        with self._lock, self._connect() as con:
            for r in con.execute("SELECT id,title,updated_at FROM sessions WHERE title LIKE ? LIMIT ?", (q, limit)).fetchall():
                results.append({"type": "chat", "id": r["id"], "title": r["title"], "detail": r["updated_at"]})
            for r in con.execute("SELECT id,name,next_run_at FROM smart_rules WHERE name LIKE ? OR command_text LIKE ? LIMIT ?", (q, q, limit)).fetchall():
                results.append({"type": "task", "id": r["id"], "title": r["name"], "detail": r["next_run_at"] or ""})
            for r in con.execute("SELECT id,name,url FROM facebook_groups WHERE name LIKE ? OR tags LIKE ? LIMIT ?", (q, q, limit)).fetchall():
                results.append({"type": "facebook", "id": r["id"], "title": r["name"], "detail": r["url"]})
            for r in con.execute("SELECT id,kind,content FROM memory_items WHERE enabled=1 AND content LIKE ? LIMIT ?", (q, limit)).fetchall():
                results.append({"type": "memory", "id": r["id"], "title": r["kind"], "detail": r["content"][:240]})
        return results[:limit]

    # ---------------- Share history ----------------
    def was_shared_recently(self, group_id: int, post_url: str, days: int) -> bool:
        if int(days) <= 0:
            return False
        cutoff = (datetime.now() - timedelta(days=int(days))).strftime("%Y-%m-%d %H:%M:%S")
        with self._lock, self._connect() as con:
            row = con.execute(
                "SELECT 1 FROM share_history WHERE group_id=? AND post_url=? AND created_at>=? AND status IN ('published','submitted','pending_approval') LIMIT 1",
                (int(group_id), post_url, cutoff),
            ).fetchone()
        return bool(row)

    def record_share(self, rule_id: int | None, group_id: int, post_url: str, status: str, detail: str = "") -> None:
        with self._lock, self._connect() as con:
            con.execute(
                "INSERT INTO share_history(rule_id,group_id,post_url,status,detail) VALUES(?,?,?,?,?)",
                (rule_id, int(group_id), post_url, status, (detail or "")[:4000]),
            )

    def submitted_share_count(self, since: datetime) -> int:
        """Count accepted submissions for the existing hourly/daily caps."""
        with self._lock, self._connect() as con:
            row = con.execute(
                "SELECT COUNT(*) FROM share_history WHERE created_at>=? "
                "AND status IN ('published','submitted','pending_approval')",
                (since.strftime("%Y-%m-%d %H:%M:%S"),),
            ).fetchone()
        return int(row[0])
