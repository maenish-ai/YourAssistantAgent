from __future__ import annotations

import json
import sqlite3
import threading
from contextlib import contextmanager
from datetime import datetime, timedelta, timezone
from typing import Any, Iterable

from .paths import db_path
from .text_utils import contains_normalized, normalize_phone
from .smart_agent import SmartPlan, calculate_next_run

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
    run_once_at TEXT NOT NULL DEFAULT '',
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

CREATE TABLE IF NOT EXISTS smart_rules (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    name TEXT NOT NULL,
    command_text TEXT NOT NULL DEFAULT '',
    source_page_url TEXT NOT NULL,
    weekdays TEXT NOT NULL DEFAULT '[]',
    run_time TEXT NOT NULL DEFAULT '20:00',
    run_once_at TEXT NOT NULL DEFAULT '',
    post_mode TEXT NOT NULL DEFAULT 'fixed',
    post_offset INTEGER NOT NULL DEFAULT 0,
    group_keyword TEXT NOT NULL DEFAULT '',
    max_groups INTEGER NOT NULL DEFAULT 100,
    interval_seconds INTEGER NOT NULL DEFAULT 60,
    no_repeat_days INTEGER NOT NULL DEFAULT 14,
    share_mode TEXT NOT NULL DEFAULT 'native_share',
    next_run_at TEXT,
    enabled INTEGER NOT NULL DEFAULT 1,
    rotation_offset INTEGER NOT NULL DEFAULT 0,
    last_run_at TEXT,
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS smart_queue_items (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    rule_id INTEGER NOT NULL,
    group_id INTEGER NOT NULL,
    post_url TEXT NOT NULL,
    scheduled_at TEXT NOT NULL,
    status TEXT NOT NULL DEFAULT 'pending',
    attempts INTEGER NOT NULL DEFAULT 0,
    last_error TEXT,
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    completed_at TEXT,
    FOREIGN KEY(rule_id) REFERENCES smart_rules(id) ON DELETE CASCADE,
    FOREIGN KEY(group_id) REFERENCES groups(id) ON DELETE CASCADE
);

CREATE TABLE IF NOT EXISTS share_history (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    rule_id INTEGER,
    group_id INTEGER NOT NULL,
    post_url TEXT NOT NULL,
    shared_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    status TEXT NOT NULL DEFAULT 'done',
    error TEXT NOT NULL DEFAULT '',
    FOREIGN KEY(rule_id) REFERENCES smart_rules(id) ON DELETE SET NULL,
    FOREIGN KEY(group_id) REFERENCES groups(id) ON DELETE CASCADE
);

CREATE TABLE IF NOT EXISTS wa_contacts (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    name TEXT NOT NULL,
    phone TEXT NOT NULL UNIQUE,
    tags TEXT NOT NULL DEFAULT '',
    opt_in INTEGER NOT NULL DEFAULT 0,
    enabled INTEGER NOT NULL DEFAULT 1,
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS wa_campaigns (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    name TEXT NOT NULL,
    message_mode TEXT NOT NULL DEFAULT 'text',
    message_text TEXT NOT NULL DEFAULT '',
    template_name TEXT NOT NULL DEFAULT '',
    template_language TEXT NOT NULL DEFAULT 'ar',
    target_keyword TEXT NOT NULL DEFAULT '',
    batch_size INTEGER NOT NULL DEFAULT 100,
    interval_seconds INTEGER NOT NULL DEFAULT 60,
    cadence_days INTEGER NOT NULL DEFAULT 1,
    run_time TEXT NOT NULL DEFAULT '19:00',
    next_run_at TEXT,
    enabled INTEGER NOT NULL DEFAULT 1,
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS wa_queue_items (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    campaign_id INTEGER,
    contact_id INTEGER NOT NULL,
    batch_no INTEGER NOT NULL DEFAULT 1,
    scheduled_at TEXT NOT NULL,
    status TEXT NOT NULL DEFAULT 'pending',
    attempts INTEGER NOT NULL DEFAULT 0,
    last_error TEXT,
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    completed_at TEXT,
    FOREIGN KEY(campaign_id) REFERENCES wa_campaigns(id) ON DELETE SET NULL,
    FOREIGN KEY(contact_id) REFERENCES wa_contacts(id) ON DELETE CASCADE
);

CREATE TABLE IF NOT EXISTS audit_log (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    ts TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    level TEXT NOT NULL,
    event TEXT NOT NULL,
    details TEXT NOT NULL DEFAULT ''
);

CREATE TABLE IF NOT EXISTS chat_messages (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    role TEXT NOT NULL,
    text TEXT NOT NULL DEFAULT '',
    attachments_json TEXT NOT NULL DEFAULT '[]',
    meta_json TEXT NOT NULL DEFAULT '{}',
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX IF NOT EXISTS idx_chat_messages_id ON chat_messages(id);

CREATE INDEX IF NOT EXISTS idx_queue_due ON queue_items(status, scheduled_at);
CREATE INDEX IF NOT EXISTS idx_campaign_next ON campaigns(enabled, next_run_at);
CREATE INDEX IF NOT EXISTS idx_wa_queue_due ON wa_queue_items(status, scheduled_at);
CREATE INDEX IF NOT EXISTS idx_wa_campaign_next ON wa_campaigns(enabled, next_run_at);
CREATE INDEX IF NOT EXISTS idx_wa_contacts_enabled ON wa_contacts(enabled, opt_in);
CREATE INDEX IF NOT EXISTS idx_smart_rule_next ON smart_rules(enabled, next_run_at);
CREATE INDEX IF NOT EXISTS idx_smart_queue_due ON smart_queue_items(status, scheduled_at);
CREATE INDEX IF NOT EXISTS idx_share_history_lookup ON share_history(group_id, post_url, shared_at);
"""


def utcnow_iso() -> str:
    return datetime.now(timezone.utc).replace(tzinfo=None, microsecond=0).isoformat()


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
            cols = {row[1] for row in con.execute("PRAGMA table_info(smart_rules)").fetchall()}
            if "run_once_at" not in cols:
                con.execute("ALTER TABLE smart_rules ADD COLUMN run_once_at TEXT NOT NULL DEFAULT ''")
            defaults = {
                "paused": False,
                "pin_hash": "",
                "first_run_done": False,
                "language": "",
                "facebook_mode": "link_post",
                "stop_on_checkpoint": True,
                "default_timezone": "Asia/Amman",
                "wa_phone_number_id": "",
                "wa_api_version": "v24.0",
                "wa_access_token_protected": "",
                "smart_default_source_page": "",
                "smart_default_interval_seconds": 60,
                "smart_default_max_groups": 100,
                "smart_no_repeat_days": 14,
                "smart_ai_enabled": False,
                "smart_ai_model": "gpt-6-luna",
                "smart_ai_last_status": {},
                "agent_ai_enabled": True,
                "agent_ai_provider": "local",
                "local_ai_profile": "auto",
                "local_ai_model_path": "",
                "external_ai_endpoint": "https://api.openai.com/v1/chat/completions",
                "external_ai_model": "",
                "smart_dialog_history": [],
                "telegram_enabled": False,
                "telegram_authorized_user_id": "",
                "auto_wake_for_smart_rules": False,
                "wake_minutes_early": 2,
                "wol_target_mac": "",
                "wol_broadcast_ip": "255.255.255.255",
                "wol_port": 9,
                "owner_name": "",
                "business_name": "",
                "auto_discover_groups": True,
                "auto_group_discovery_attempted": False,
                "cloud_backup_folder": "",
                "cloud_backup_enabled": False,
                "cloud_backup_interval_hours": 6,
                "cloud_backup_keep_versions": 7,
                "cloud_backup_last_at": "",
                "cloud_backup_last_file": "",
                "chat_pending_plan": {},
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
                (level, event, str(details)[:4000]),
            )

    # Facebook groups
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
        sql = "SELECT * FROM groups"
        if enabled_only:
            sql += " WHERE enabled=1"
        sql += " ORDER BY name COLLATE NOCASE"
        with self.conn() as con:
            rows = con.execute(sql).fetchall()
        if keyword:
            rows = [r for r in rows if contains_normalized(f"{r['name']} {r['tags']}", keyword)]
        if limit:
            rows = rows[: int(limit)]
        return rows

    def count_groups(self, enabled_only=False, keyword: str | None = None) -> int:
        """Return the real number of matching saved groups without execution limits."""
        return len(self.list_groups(enabled_only=enabled_only, keyword=keyword, limit=None))

    # Facebook campaigns
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
        if camp:
            self._bump_table("campaigns", campaign_id, camp["next_run_at"], camp["cadence_days"])

    # Facebook queue
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

    # Smart Agent rules and queue
    def upsert_discovered_groups(self, groups: Iterable[dict]) -> int:
        count = 0
        with self.conn() as con:
            for g in groups:
                name = str(g.get("name") or "").strip()
                url = str(g.get("url") or "").strip()
                tags = str(g.get("tags") or "").strip()
                if not name or not url:
                    continue
                con.execute(
                    """INSERT INTO groups(name,url,tags) VALUES (?,?,?)
                       ON CONFLICT(url) DO UPDATE SET name=excluded.name""",
                    (name, url, tags),
                )
                count += 1
        if count:
            self.audit("INFO", "groups_discovered", str(count))
        return count

    def add_smart_rule(self, plan: SmartPlan | dict) -> int:
        if isinstance(plan, SmartPlan):
            data = plan.to_dict()
        else:
            data = dict(plan)
        weekdays = sorted(set(int(d) for d in data.get("weekdays", []) if 0 <= int(d) <= 6))
        run_time = str(data.get("run_time") or "20:00")
        run_once_at = str(data.get("run_once_at") or "").strip()
        next_run = run_once_at or calculate_next_run(weekdays, run_time)
        with self.conn() as con:
            cur = con.execute(
                """INSERT INTO smart_rules
                   (name,command_text,source_page_url,weekdays,run_time,run_once_at,post_mode,post_offset,
                    group_keyword,max_groups,interval_seconds,no_repeat_days,share_mode,next_run_at)
                   VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
                (
                    str(data.get("name") or "Smart rule").strip(),
                    str(data.get("command_text") or "").strip(),
                    str(data.get("source_page_url") or "").strip(),
                    json.dumps(weekdays), run_time, run_once_at,
                    "rotation" if data.get("post_mode") == "rotation" else "fixed",
                    max(0, int(data.get("post_offset", 0))),
                    str(data.get("group_keyword") or "").strip(),
                    max(1, min(500, int(data.get("max_groups", 100)))),
                    max(30, int(data.get("interval_seconds", 60))),
                    max(0, int(data.get("no_repeat_days", 14))),
                    str(data.get("share_mode") or "native_share"),
                    next_run,
                ),
            )
            rule_id = int(cur.lastrowid)
        self.audit("INFO", "smart_rule_added", f"{rule_id}: {data.get('name','')}")
        return rule_id

    def update_smart_rule(self, rule_id: int, plan: SmartPlan | dict):
        data = plan.to_dict() if isinstance(plan, SmartPlan) else dict(plan)
        weekdays = sorted(set(int(d) for d in data.get("weekdays", []) if 0 <= int(d) <= 6))
        run_time = str(data.get("run_time") or "20:00")
        run_once_at = str(data.get("run_once_at") or "").strip()
        next_run = run_once_at or calculate_next_run(weekdays, run_time)
        with self.conn() as con:
            con.execute(
                """UPDATE smart_rules SET name=?,command_text=?,source_page_url=?,weekdays=?,run_time=?,run_once_at=?,
                   post_mode=?,post_offset=?,group_keyword=?,max_groups=?,interval_seconds=?,no_repeat_days=?,
                   share_mode=?,next_run_at=?,enabled=1 WHERE id=?""",
                (
                    str(data.get("name") or "Smart rule").strip(), str(data.get("command_text") or "").strip(),
                    str(data.get("source_page_url") or "").strip(), json.dumps(weekdays), run_time, run_once_at,
                    "rotation" if data.get("post_mode") == "rotation" else "fixed", max(0, int(data.get("post_offset", 0))),
                    str(data.get("group_keyword") or "").strip(), max(1, min(500, int(data.get("max_groups", 100)))),
                    max(30, int(data.get("interval_seconds", 60))), max(0, int(data.get("no_repeat_days", 14))),
                    str(data.get("share_mode") or "native_share"), next_run, int(rule_id),
                ),
            )
        self.audit("INFO", "smart_rule_updated", f"{rule_id}: {data.get('name','')}")

    def cancel_smart_rule_pending(self, rule_id: int) -> int:
        with self.conn() as con:
            cur = con.execute(
                "UPDATE smart_queue_items SET status='cancelled',completed_at=? WHERE rule_id=? AND status='pending'",
                (utcnow_iso(), int(rule_id)),
            )
            return int(cur.rowcount or 0)

    def next_smart_rule_time(self) -> str:
        with self.conn() as con:
            row = con.execute(
                "SELECT MIN(next_run_at) AS t FROM smart_rules WHERE enabled=1 AND next_run_at IS NOT NULL"
            ).fetchone()
        return str(row["t"] or "") if row else ""

    def list_smart_rules(self):
        with self.conn() as con:
            return con.execute("SELECT * FROM smart_rules ORDER BY id DESC").fetchall()

    def get_smart_rule(self, rule_id: int):
        with self.conn() as con:
            return con.execute("SELECT * FROM smart_rules WHERE id=?", (rule_id,)).fetchone()

    def update_smart_rule_enabled(self, rule_id: int, enabled: bool):
        with self.conn() as con:
            con.execute("UPDATE smart_rules SET enabled=? WHERE id=?", (int(bool(enabled)), rule_id))

    def delete_smart_rule(self, rule_id: int):
        with self.conn() as con:
            con.execute("DELETE FROM smart_rules WHERE id=?", (rule_id,))

    def due_smart_rules(self, now_iso: str):
        with self.conn() as con:
            return con.execute(
                "SELECT * FROM smart_rules WHERE enabled=1 AND next_run_at IS NOT NULL AND next_run_at<=? ORDER BY next_run_at",
                (now_iso,),
            ).fetchall()

    @staticmethod
    def smart_rule_weekdays(rule) -> list[int]:
        try:
            return [int(x) for x in json.loads(rule["weekdays"] or "[]")]
        except Exception:
            return []

    def bump_smart_rule(self, rule_id: int, advance_rotation: bool = False):
        rule = self.get_smart_rule(rule_id)
        if not rule:
            return
        if "run_once_at" in rule.keys() and str(rule["run_once_at"] or ""):
            with self.conn() as con:
                con.execute("UPDATE smart_rules SET enabled=0,next_run_at=NULL,last_run_at=? WHERE id=?", (utcnow_iso(), rule_id))
            return
        next_run = calculate_next_run(self.smart_rule_weekdays(rule), rule["run_time"])
        with self.conn() as con:
            if advance_rotation and rule["post_mode"] == "rotation":
                con.execute(
                    "UPDATE smart_rules SET next_run_at=?,last_run_at=?,rotation_offset=rotation_offset+1 WHERE id=?",
                    (next_run, utcnow_iso(), rule_id),
                )
            else:
                con.execute(
                    "UPDATE smart_rules SET next_run_at=?,last_run_at=? WHERE id=?",
                    (next_run, utcnow_iso(), rule_id),
                )

    def advance_smart_rotation(self, rule_id: int):
        with self.conn() as con:
            con.execute("UPDATE smart_rules SET rotation_offset=rotation_offset+1,last_run_at=? WHERE id=?", (utcnow_iso(), rule_id))

    def enqueue_smart(self, rule_id: int, group_ids: Iterable[int], post_url: str, interval_seconds: int) -> int:
        start = datetime.now()
        rows = []
        for i, gid in enumerate(group_ids):
            when = start + timedelta(seconds=i * max(30, int(interval_seconds)))
            rows.append((rule_id, int(gid), post_url, when.replace(microsecond=0).isoformat()))
        with self.conn() as con:
            con.executemany(
                "INSERT INTO smart_queue_items(rule_id,group_id,post_url,scheduled_at) VALUES (?,?,?,?)",
                rows,
            )
        return len(rows)

    def next_due_smart_queue_item(self, now_iso: str):
        with self.conn() as con:
            return con.execute(
                """SELECT q.*, g.name AS group_name, g.url AS group_url,
                          r.name AS rule_name, r.share_mode AS share_mode
                   FROM smart_queue_items q
                   JOIN groups g ON g.id=q.group_id
                   JOIN smart_rules r ON r.id=q.rule_id
                   WHERE q.status='pending' AND q.scheduled_at<=?
                   ORDER BY q.scheduled_at, q.id LIMIT 1""",
                (now_iso,),
            ).fetchone()

    def mark_smart_queue(self, item_id: int, status: str, error: str = ""):
        completed = utcnow_iso() if status in {"done", "published", "submitted", "pending_approval", "failed", "blocked", "cancelled", "skipped"} else None
        with self.conn() as con:
            con.execute(
                "UPDATE smart_queue_items SET status=?,attempts=attempts+1,last_error=?,completed_at=? WHERE id=?",
                (status, error[:2000], completed, item_id),
            )

    def was_shared_recently(self, group_id: int, post_url: str, no_repeat_days: int) -> bool:
        days = max(0, int(no_repeat_days))
        if days <= 0:
            return False
        threshold = (datetime.now(timezone.utc).replace(tzinfo=None) - timedelta(days=days)).replace(microsecond=0).isoformat()
        with self.conn() as con:
            row = con.execute(
                """SELECT 1 FROM share_history
                   WHERE group_id=? AND post_url=?
                     AND status IN ('done','published','submitted','pending_approval')
                     AND shared_at>=?
                   LIMIT 1""",
                (group_id, post_url, threshold),
            ).fetchone()
        return bool(row)

    def record_share(self, rule_id: int | None, group_id: int, post_url: str, status: str, error: str = ""):
        with self.conn() as con:
            con.execute(
                "INSERT INTO share_history(rule_id,group_id,post_url,shared_at,status,error) VALUES (?,?,?,?,?,?)",
                (rule_id, group_id, post_url, utcnow_iso(), status, error[:2000]),
            )

    def smart_queue_stats(self):
        with self.conn() as con:
            return {r["status"]: r["n"] for r in con.execute(
                "SELECT status,COUNT(*) n FROM smart_queue_items GROUP BY status"
            ).fetchall()}

    # WhatsApp contacts
    def add_wa_contact(self, name: str, phone: str, tags: str = "", opt_in: bool = False):
        number = normalize_phone(phone)
        with self.conn() as con:
            con.execute(
                "INSERT INTO wa_contacts(name,phone,tags,opt_in) VALUES (?,?,?,?)",
                (name.strip(), number, tags.strip(), int(bool(opt_in))),
            )
        self.audit("INFO", "wa_contact_added", f"{name}: {number}")

    def upsert_wa_contact(self, name: str, phone: str, tags: str = "", opt_in: bool = False):
        number = normalize_phone(phone)
        with self.conn() as con:
            con.execute(
                """INSERT INTO wa_contacts(name,phone,tags,opt_in) VALUES (?,?,?,?)
                   ON CONFLICT(phone) DO UPDATE SET name=excluded.name,tags=excluded.tags,opt_in=excluded.opt_in""",
                (name.strip(), number, tags.strip(), int(bool(opt_in))),
            )

    def delete_wa_contact(self, contact_id: int):
        with self.conn() as con:
            con.execute("DELETE FROM wa_contacts WHERE id=?", (contact_id,))

    def list_wa_contacts(self, enabled_only=False, opted_in_only=False, keyword: str | None = None, limit: int | None = None):
        clauses = []
        if enabled_only:
            clauses.append("enabled=1")
        if opted_in_only:
            clauses.append("opt_in=1")
        sql = "SELECT * FROM wa_contacts"
        if clauses:
            sql += " WHERE " + " AND ".join(clauses)
        sql += " ORDER BY name COLLATE NOCASE"
        with self.conn() as con:
            rows = con.execute(sql).fetchall()
        if keyword:
            rows = [r for r in rows if contains_normalized(f"{r['name']} {r['tags']} {r['phone']}", keyword)]
        if limit:
            rows = rows[: int(limit)]
        return rows

    # WhatsApp campaigns
    def add_wa_campaign(
        self,
        name: str,
        message_mode: str,
        message_text: str,
        template_name: str,
        template_language: str,
        target_keyword: str,
        batch_size: int,
        interval_seconds: int,
        cadence_days: int,
        run_time: str,
    ):
        next_run = self.compute_next_run(cadence_days, run_time)
        mode = message_mode if message_mode in {"text", "template"} else "text"
        with self.conn() as con:
            con.execute(
                """INSERT INTO wa_campaigns
                   (name,message_mode,message_text,template_name,template_language,target_keyword,batch_size,interval_seconds,cadence_days,run_time,next_run_at)
                   VALUES (?,?,?,?,?,?,?,?,?,?,?)""",
                (
                    name.strip(), mode, message_text.strip(), template_name.strip(), template_language.strip() or "ar",
                    target_keyword.strip(), max(1, min(256, int(batch_size))), max(30, int(interval_seconds)),
                    max(1, int(cadence_days)), run_time, next_run,
                ),
            )
        self.audit("INFO", "wa_campaign_added", name)

    def list_wa_campaigns(self):
        with self.conn() as con:
            return con.execute("SELECT * FROM wa_campaigns ORDER BY id DESC").fetchall()

    def get_wa_campaign(self, campaign_id: int):
        with self.conn() as con:
            return con.execute("SELECT * FROM wa_campaigns WHERE id=?", (campaign_id,)).fetchone()

    def update_wa_campaign_enabled(self, campaign_id: int, enabled: bool):
        with self.conn() as con:
            con.execute("UPDATE wa_campaigns SET enabled=? WHERE id=?", (int(enabled), campaign_id))

    def delete_wa_campaign(self, campaign_id: int):
        with self.conn() as con:
            con.execute("DELETE FROM wa_campaigns WHERE id=?", (campaign_id,))

    def due_wa_campaigns(self, now_iso: str):
        with self.conn() as con:
            return con.execute(
                "SELECT * FROM wa_campaigns WHERE enabled=1 AND next_run_at IS NOT NULL AND next_run_at<=? ORDER BY next_run_at",
                (now_iso,),
            ).fetchall()

    def bump_wa_campaign(self, campaign_id: int):
        camp = self.get_wa_campaign(campaign_id)
        if camp:
            self._bump_table("wa_campaigns", campaign_id, camp["next_run_at"], camp["cadence_days"])

    def enqueue_wa(self, campaign_id: int, contact_ids: Iterable[int], batch_size: int, interval_seconds: int):
        start = datetime.now()
        batch_size = max(1, min(256, int(batch_size)))
        interval_seconds = max(30, int(interval_seconds))
        rows = []
        for i, cid in enumerate(contact_ids):
            batch_no = i // batch_size + 1
            when = start + timedelta(seconds=i * interval_seconds)
            rows.append((campaign_id, cid, batch_no, when.replace(microsecond=0).isoformat()))
        with self.conn() as con:
            con.executemany(
                "INSERT INTO wa_queue_items(campaign_id,contact_id,batch_no,scheduled_at) VALUES (?,?,?,?)",
                rows,
            )
        return len(rows), (0 if not rows else rows[-1][2])

    def next_due_wa_queue_item(self, now_iso: str):
        with self.conn() as con:
            return con.execute(
                """SELECT q.*, c.name AS contact_name, c.phone AS contact_phone,
                          wc.message_mode, wc.message_text, wc.template_name, wc.template_language,
                          wc.name AS campaign_name
                   FROM wa_queue_items q
                   JOIN wa_contacts c ON c.id=q.contact_id
                   LEFT JOIN wa_campaigns wc ON wc.id=q.campaign_id
                   WHERE q.status='pending' AND q.scheduled_at<=?
                   ORDER BY q.scheduled_at, q.id LIMIT 1""",
                (now_iso,),
            ).fetchone()

    def mark_wa_queue(self, item_id: int, status: str, error: str = ""):
        completed = utcnow_iso() if status in {"done", "failed", "blocked", "cancelled"} else None
        with self.conn() as con:
            con.execute(
                "UPDATE wa_queue_items SET status=?, attempts=attempts+1, last_error=?, completed_at=? WHERE id=?",
                (status, error[:2000], completed, item_id),
            )

    def queue_stats(self):
        with self.conn() as con:
            rows = con.execute("SELECT status,COUNT(*) n FROM queue_items GROUP BY status").fetchall()
        return {r["status"]: r["n"] for r in rows}

    def wa_queue_stats(self):
        with self.conn() as con:
            rows = con.execute("SELECT status,COUNT(*) n FROM wa_queue_items GROUP BY status").fetchall()
        return {r["status"]: r["n"] for r in rows}

    def clear_pending(self):
        now = utcnow_iso()
        with self.conn() as con:
            con.execute("UPDATE queue_items SET status='cancelled', completed_at=? WHERE status='pending'", (now,))
            con.execute("UPDATE wa_queue_items SET status='cancelled', completed_at=? WHERE status='pending'", (now,))

    # Chat-first assistant history
    def add_chat_message(self, role: str, text: str, attachments=None, meta=None) -> int:
        attachments = list(attachments or [])
        meta = dict(meta or {})
        with self.conn() as con:
            cur = con.execute(
                "INSERT INTO chat_messages(role,text,attachments_json,meta_json) VALUES (?,?,?,?)",
                (str(role), str(text), json.dumps(attachments, ensure_ascii=False), json.dumps(meta, ensure_ascii=False)),
            )
            return int(cur.lastrowid)

    def list_chat_messages(self, limit: int = 100):
        limit = max(1, min(int(limit), 1000))
        with self.conn() as con:
            rows = con.execute(
                "SELECT * FROM chat_messages ORDER BY id DESC LIMIT ?", (limit,)
            ).fetchall()
        return list(reversed(rows))

    def clear_chat_messages(self):
        with self.conn() as con:
            con.execute("DELETE FROM chat_messages")
        self.set_setting("chat_pending_plan", {})
        self.audit("INFO", "chat_history_cleared")

    def chat_context_text(self, limit: int = 20) -> str:
        lines = []
        for row in self.list_chat_messages(limit=limit):
            role = str(row["role"] or "user")
            text = str(row["text"] or "")
            lines.append(f"{role.upper()}: {text}")
        return "\n".join(lines)

    def recent_audit(self, limit=200):
        with self.conn() as con:
            return con.execute("SELECT * FROM audit_log ORDER BY id DESC LIMIT ?", (limit,)).fetchall()

    @staticmethod
    def compute_next_run(cadence_days: int, run_time: str) -> str:
        hour, minute = [int(x) for x in run_time.split(":", 1)]
        now = datetime.now()
        candidate = now.replace(hour=hour, minute=minute, second=0, microsecond=0)
        if candidate <= now:
            candidate += timedelta(days=max(1, int(cadence_days)))
        return candidate.isoformat()

    def _bump_table(self, table: str, row_id: int, next_run_at: str | None, cadence_days: int):
        try:
            base = datetime.fromisoformat(next_run_at) if next_run_at else datetime.now()
        except Exception:
            base = datetime.now()
        now = datetime.now()
        while base <= now:
            base += timedelta(days=max(1, int(cadence_days)))
        if table not in {"campaigns", "wa_campaigns"}:
            raise ValueError("Invalid schedule table")
        with self.conn() as con:
            con.execute(f"UPDATE {table} SET next_run_at=? WHERE id=?", (base.replace(microsecond=0).isoformat(), row_id))
