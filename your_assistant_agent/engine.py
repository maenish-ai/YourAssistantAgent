from __future__ import annotations

import queue
import threading
import time
from datetime import datetime
from typing import Any

from .db import Database
from .facebook import CheckpointDetected, FacebookAutomation, FacebookError, LoginRequired


class AgentEngine(threading.Thread):
    def __init__(self, db: Database):
        super().__init__(name="YourAssistantAgentEngine", daemon=True)
        self.db = db
        self.stop_event = threading.Event()
        self.commands: queue.Queue[tuple[str, Any]] = queue.Queue()
        self.fb = FacebookAutomation()

    def command(self, name: str, payload=None):
        self.commands.put((name, payload))

    def shutdown(self):
        self.stop_event.set()
        self.command("shutdown")

    def run(self):
        self.db.audit("INFO", "engine_started")
        while not self.stop_event.is_set():
            try:
                self._handle_commands()
                if not self.db.get_setting("paused", False):
                    self._schedule_due_campaigns()
                    self._process_due_queue()
            except Exception as exc:
                self.db.audit("ERROR", "engine_loop_error", repr(exc))
            self.stop_event.wait(1.0)
        try:
            self.fb.stop()
        except Exception:
            pass
        self.db.audit("INFO", "engine_stopped")

    def _handle_commands(self):
        while True:
            try:
                name, payload = self.commands.get_nowait()
            except queue.Empty:
                break
            if name == "shutdown":
                return
            if name == "open_login":
                try:
                    self.fb.open_login()
                    self.db.audit("INFO", "facebook_browser_opened")
                except Exception as exc:
                    self.db.audit("ERROR", "facebook_browser_error", str(exc))
            elif name == "run_campaign_now":
                try:
                    camp = self.db.get_campaign(int(payload))
                    if camp:
                        self._create_campaign_queue(camp)
                except Exception as exc:
                    self.db.audit("ERROR", "manual_campaign_error", str(exc))

    def _schedule_due_campaigns(self):
        now = datetime.now().replace(microsecond=0).isoformat()
        for camp in self.db.due_campaigns(now):
            try:
                self._create_campaign_queue(camp)
            finally:
                self.db.bump_campaign(camp["id"])

    def _create_campaign_queue(self, camp):
        self.db.audit("INFO", "campaign_start", camp["name"])
        groups = self.db.list_groups(
            enabled_only=True,
            keyword=camp["group_keyword"] or None,
            limit=int(camp["max_groups"]),
        )
        if not groups:
            self.db.audit("WARNING", "campaign_no_groups", camp["name"])
            return

        try:
            self.fb.ensure_logged_in()
            posts = self.fb.find_recent_post_urls(camp["source_page_url"], limit=max(8, int(camp["post_offset"]) + 3))
        except LoginRequired:
            self.db.audit("WARNING", "facebook_login_required", camp["name"])
            return
        except CheckpointDetected as exc:
            self.db.set_setting("paused", True)
            self.db.audit("SECURITY", "facebook_checkpoint", str(exc))
            return
        except Exception as exc:
            self.db.audit("ERROR", "post_discovery_failed", f"{camp['name']}: {exc}")
            return

        offset = int(camp["post_offset"])
        if offset >= len(posts):
            self.db.audit("ERROR", "post_offset_missing", f"{camp['name']}: found {len(posts)} posts, offset={offset}")
            return

        post_url = posts[offset]
        count = self.db.enqueue(camp["id"], [g["id"] for g in groups], post_url, int(camp["interval_seconds"]))
        self.db.audit("INFO", "campaign_queued", f"{camp['name']}: {count} groups; source={post_url}")

    def _process_due_queue(self):
        item = self.db.next_due_queue_item(datetime.now().replace(microsecond=0).isoformat())
        if not item:
            return
        try:
            self.fb.ensure_logged_in()
            self.fb.post_link_to_group(
                group_url=item["group_url"],
                post_url=item["post_url"],
                message_prefix=item["message_prefix"] or "",
            )
            self.db.mark_queue(item["id"], "done")
            self.db.audit("INFO", "group_post_done", item["group_name"])
        except LoginRequired as exc:
            self.db.mark_queue(item["id"], "failed", str(exc))
            self.db.set_setting("paused", True)
            self.db.audit("WARNING", "facebook_login_required", item["group_name"])
        except CheckpointDetected as exc:
            self.db.mark_queue(item["id"], "blocked", str(exc))
            self.db.set_setting("paused", True)
            self.db.audit("SECURITY", "facebook_checkpoint", item["group_name"])
        except FacebookError as exc:
            self.db.mark_queue(item["id"], "failed", str(exc))
            self.db.audit("ERROR", "group_post_failed", f"{item['group_name']}: {exc}")
        except Exception as exc:
            self.db.mark_queue(item["id"], "failed", repr(exc))
            self.db.audit("ERROR", "group_post_failed", f"{item['group_name']}: {repr(exc)}")
