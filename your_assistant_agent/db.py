from __future__ import annotations

import json
import sqlite3
import threading
from contextlib import contextmanager
from datetime import datetime, timedelta
from typing import Any, Iterable

from .paths import db_path

DB_LOCK = threading.RLock()

SCHEMA = """
PRAGMA journal_mode=WAL;
PRAGMA foreign_keys=ON;

CREATE TABLE IF NOT EXISTS settings (
    key TEXT PRIMARY KEY,
    value TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS groups (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    name TEXT NOT NULL,
    url TEXT NOT NULL UNIQUE,
    tags TEXT NOT NULL DEFAULT '',
    enabled INTEGER NOT NULL DEFAULT 1,
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS campaigns (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    name TEXT NOT NULL,
    source_page_url TEXT NOT NULL,
    post_offset INTEGER NOT NULL DEFAULT 0,
    group_keyword TEXT NOT NULL DEFAULT '',
    max_groups INTEGER NOT NULL DEFAULT 10,
    interval_seconds INTEGER NOT NULL DEFAULT 60,
    message_prefix TEXT NOT NULL DEFAULT '',
    cadence_days INTEGER NOT NULL DEFAULT 3,
    run_time TEXT NOT NULL DEFAULT '20:00',
    next_run_at TEXT,
    enabled INTEGER NOT NULL DEFAULT 1,
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS queue_items (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    campaign_id INTEGER,
    group_id INTEGER NOT NULL,
    post_url TEXT NOT NULL,
    scheduled_at TEXT NOT NULL,
    status TEXT NOT NULL DEFAULT 'pending',
    attempts INTEGER NOT NULL DEFAULT 0,
    last_error TEXT,
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    completed_at TEXT,
    FOREIGN KEY(campaign_id) REFERENCES campaigns(id) ON DELETE SET NULL,
    FOREIGN KEY(group_id) REFERENCES groups(id) ON DELETE CASCADE
);

CREATE TABLE IF NOT EXISTS audit_log (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    ts TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    level TEXT NOT NULL,
    event TEXT NOT NULL,
    details TEXT NOT NULL DEFAULT ''
);

CREATE INDEX IF NOT EXISTS idx_queue_due ON queue_items(status, scheduled_at);
CREATE INDEX IF NOT EXISTS idx_campaign_next ON campaigns(enabled, next_run_at);
"""


def utcnow_iso() -> str:
    return datetime.utcnow().replace(microsecond=0).isoformat()


class Database:
    def __init__(self, path=None):
        self.path = str(path or db_path())
        self.init()

    @contextmanager
    def conn(self):
        with DB_LOCK:
            con = sqlite3.connect(self.path, timeout=30)
            con.row_factory = sqlite3.Row
            try:
                yield con
                con.commit()
            finally:
                con.close()

    def init(self):
        with self.conn() as con:
            con.executescript(SCHEMA)
            defaults = {
                "paused": False,
                "pin_hash": "",
                "first_run_done": False,
                "facebook_mode": "link_post",
                "stop_on_checkpoint": True,
                "default_timezone": "Asia/Amman",
            }
            for k, v in defaults.items():
                con.execute(
                    "INSERT OR IGNORE INTO settings(key,value) VALUES (?,?)",
                    (k, json.dumps(v, ensure_ascii=False)),
                )

    def get_setting(self, key: str, default=None):
        with self.conn() as con:
            row = con.execute("SELECT value FROM settings WHERE key=?", (key,)).fetchone()
        if not row:
            return default
        try:
            return json.loads(row["value"])
        except Exception:
            return row["value"]

    def set_setting(self, key: str, value: Any):
        data = json.dumps(value, ensure_ascii=False)
        with self.conn() as con:
            con.execute(
                "INSERT INTO settings(key,value) VALUES (?,?) ON CONFLICT(key) DO UPDATE SET value=excluded.value",
                (key, data),
            )

    def audit(self, level: str, event: str, details: str = ""):
        with self.conn() as con:
            con.execute(
                "INSERT INTO audit_log(level,event,details) VALUES (?,?,?)",
                (level, event, details[:4000]),
            )

    # Groups
    def add_group(self, name: str, url: str, tags: str = ""):
        with self.conn() as con:
            con.execute(
                "INSERT INTO groups(name,url,tags) VALUES (?,?,?)",
                (name.strip(), url.strip(), tags.strip()),
            )
        self.audit("INFO", "group_added", name)

    def update_group(self, group_id: int, name: str, url: str, tags: str, enabled: bool):
        with self.conn() as con:
            con.execute(
                "UPDATE groups SET name=?,url=?,tags=?,enabled=? WHERE id=?",
                (name.strip(), url.strip(), tags.strip(), int(enabled), group_id),
            )

    def delete_group(self, group_id: int):
        with self.conn() as con:
            con.execute("DELETE FROM groups WHERE id=?", (group_id,))

    def list_groups(self, enabled_only=False, keyword: str | None = None, limit: int | None = None):
        sql = "SELECT * FROM groups WHERE 1=1"
        args: list[Any] = []
        if enabled_only:
            sql += " AND enabled=1"
        if keyword:
            sql += " AND (name LIKE ? OR tags LIKE ?)"
            needle = f"%{keyword}%"
            args += [needle, needle]
        sql += " ORDER BY name COLLATE NOCASE"
        if limit:
            sql += " LIMIT ?"
            args.append(limit)
        with self.conn() as con:
            return con.execute(sql, args).fetchall()

    # Campaigns
    def add_campaign(
        self,
        name: str,
        source_page_url: str,
        post_offset: int,
        group_keyword: str,
        max_groups: int,
        interval_seconds: int,
        cadence_days: int,
        run_time: str,
        message_prefix: str = "",
    ):
        next_run = self.compute_next_run(cadence_days, run_time)
        with self.conn() as con:
            con.execute(
                """INSERT INTO campaigns
                (name,source_page_url,post_offset,group_keyword,max_groups,interval_seconds,message_prefix,cadence_days,run_time,next_run_at)
                VALUES (?,?,?,?,?,?,?,?,?,?)""",
                (
                    name.strip(), source_page_url.strip(), int(post_offset), group_keyword.strip(),
                    int(max_groups), max(30, int(interval_seconds)), message_prefix.strip(),
                    max(1, int(cadence_days)), run_time, next_run,
                ),
            )
        self.audit("INFO", "campaign_added", name)

    def update_campaign_enabled(self, campaign_id: int, enabled: bool):
        with self.conn() as con:
            con.execute("UPDATE campaigns SET enabled=? WHERE id=?", (int(enabled), campaign_id))

    def delete_campaign(self, campaign_id: int):
        with self.conn() as con:
            con.execute("DELETE FROM campaigns WHERE id=?", (campaign_id,))

    def list_campaigns(self):
        with self.conn() as con:
            return con.execute("SELECT * FROM campaigns ORDER BY id DESC").fetchall()

    def get_campaign(self, campaign_id: int):
        with self.conn() as con:
            return con.execute("SELECT * FROM campaigns WHERE id=?", (campaign_id,)).fetchone()

    def due_campaigns(self, now_iso: str):
        with self.conn() as con:
            return con.execute(
                "SELECT * FROM campaigns WHERE enabled=1 AND next_run_at IS NOT NULL AND next_run_at<=? ORDER BY next_run_at",
                (now_iso,),
            ).fetchall()

    def bump_campaign(self, campaign_id: int):
        camp = self.get_campaign(campaign_id)
        if not camp:
            return
        try:
            base = datetime.fromisoformat(camp["next_run_at"]) if camp["next_run_at"] else datetime.now()
        except Exception:
            base = datetime.now()
        now = datetime.now()
        while base <= now:
            base += timedelta(days=max(1, int(camp["cadence_days"])))
        with self.conn() as con:
            con.execute("UPDATE campaigns SET next_run_at=? WHERE id=?", (base.replace(microsecond=0).isoformat(), campaign_id))

    @staticmethod
    def compute_next_run(cadence_days: int, run_time: str) -> str:
        hour, minute = [int(x) for x in run_time.split(":", 1)]
        now = datetime.now()
        candidate = now.replace(hour=hour, minute=minute, second=0, microsecond=0)
        if candidate <= now:
            candidate += timedelta(days=max(1, int(cadence_days)))
        return candidate.isoformat()

    # Queue
    def enqueue(self, campaign_id: int | None, group_ids: Iterable[int], post_url: str, interval_seconds: int):
        start = datetime.now()
        rows = []
        for i, gid in enumerate(group_ids):
            when = start + timedelta(seconds=i * max(30, int(interval_seconds)))
            rows.append((campaign_id, gid, post_url, when.replace(microsecond=0).isoformat()))
        with self.conn() as con:
            con.executemany(
                "INSERT INTO queue_items(campaign_id,group_id,post_url,scheduled_at) VALUES (?,?,?,?)",
                rows,
            )
        return len(rows)

    def next_due_queue_item(self, now_iso: str):
        with self.conn() as con:
            return con.execute(
                """SELECT q.*, g.name AS group_name, g.url AS group_url,
                          c.message_prefix AS message_prefix
                   FROM queue_items q
                   JOIN groups g ON g.id=q.group_id
                   LEFT JOIN campaigns c ON c.id=q.campaign_id
                   WHERE q.status='pending' AND q.scheduled_at<=?
                   ORDER BY q.scheduled_at, q.id LIMIT 1""",
                (now_iso,),
            ).fetchone()

    def mark_queue(self, item_id: int, status: str, error: str = ""):
        completed = utcnow_iso() if status in {"done", "failed", "blocked", "cancelled"} else None
        with self.conn() as con:
            con.execute(
                "UPDATE queue_items SET status=?, attempts=attempts+1, last_error=?, completed_at=? WHERE id=?",
                (status, error[:2000], completed, item_id),
            )

    def queue_stats(self):
        with self.conn() as con:
            rows = con.execute("SELECT status,COUNT(*) n FROM queue_items GROUP BY status").fetchall()
        return {r["status"]: r["n"] for r in rows}

    def clear_pending(self):
        with self.conn() as con:
            con.execute("UPDATE queue_items SET status='cancelled', completed_at=? WHERE status='pending'", (utcnow_iso(),))

    def recent_audit(self, limit=200):
        with self.conn() as con:
            return con.execute("SELECT * FROM audit_log ORDER BY id DESC LIMIT ?", (limit,)).fetchall()
