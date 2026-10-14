from __future__ import annotations

import queue
import threading
import time
from datetime import datetime
from typing import Any

from .db import Database
from .facebook import CheckpointDetected, FacebookAutomation, FacebookConfig, FacebookError, LoginRequired
from .security import SecurityManager
from .whatsapp import WhatsAppBusinessClient, WhatsAppError, WhatsAppNotConfigured


class AgentEngine(threading.Thread):
    def __init__(self, db: Database, security: SecurityManager):
        super().__init__(name="YourAssistantAgentEngine", daemon=True)
        self.db = db
        self.security = security
        self.stop_event = threading.Event()
        self.commands: queue.Queue[tuple[str, Any]] = queue.Queue()
        language = db.get_setting("language", "en") or "en"
        self.facebook_locale = "ar-JO" if language == "ar" else "en-US"
        browser_choice = str(db.get_setting("facebook_browser_choice", "auto") or "auto")
        browser_label = str(db.get_setting("facebook_browser_label", "") or "")
        self.fb = FacebookAutomation(FacebookConfig(
            locale=self.facebook_locale,
            browser_choice=browser_choice,
            browser_label=browser_label,
        ))
        self.wa = WhatsAppBusinessClient(db, security)
        self._last_fb_status_poll = 0.0

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
                self._poll_facebook_status()
                if not self.db.get_setting("paused", False):
                    self._schedule_due_facebook_campaigns()
                    self._schedule_due_whatsapp_campaigns()
                    self._process_due_facebook_queue()
                    self._process_due_whatsapp_queue()
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
                    self.db.set_setting("facebook_browser_backend", self.fb.browser_backend)
                    self.db.set_setting("facebook_connection_status", self.fb.connection_status())
                    self.db.set_setting("facebook_browser_last_error", "")
                    self.db.audit("INFO", "facebook_browser_opened", self.fb.browser_backend)
                except Exception as exc:
                    self.db.set_setting("facebook_connection_status", "browser_error")
                    self.db.set_setting("facebook_browser_last_error", str(exc))
                    self.db.audit("ERROR", "facebook_browser_error", str(exc))
            elif name == "check_facebook_connection":
                self.db.set_setting("facebook_connection_status", self.fb.connection_status())
                self.db.set_setting("facebook_browser_backend", self.fb.browser_backend)
            elif name == "set_facebook_browser":
                data = payload or {}
                choice = str(data.get("choice") or "auto")
                label = str(data.get("label") or "")
                try:
                    self.fb.stop()
                except Exception:
                    pass
                self.db.set_setting("facebook_browser_choice", choice)
                self.db.set_setting("facebook_browser_label", label)
                self.db.set_setting("facebook_browser_backend", "")
                self.db.set_setting("facebook_connection_status", "not_checked")
                self.db.set_setting("facebook_browser_user_selected", True)
                self.fb = FacebookAutomation(FacebookConfig(
                    locale=self.facebook_locale,
                    browser_choice=choice,
                    browser_label=label,
                ))
                self.db.audit("INFO", "facebook_browser_changed", label or choice)
            elif name == "run_campaign_now":
                try:
                    camp = self.db.get_campaign(int(payload))
                    if camp:
                        self._create_facebook_campaign_queue(camp)
                except Exception as exc:
                    self.db.audit("ERROR", "manual_campaign_error", str(exc))
            elif name == "run_wa_campaign_now":
                try:
                    camp = self.db.get_wa_campaign(int(payload))
                    if camp:
                        self._create_whatsapp_campaign_queue(camp)
                except Exception as exc:
                    self.db.audit("ERROR", "wa_manual_campaign_error", str(exc))

    def _poll_facebook_status(self):
        now = time.monotonic()
        if now - self._last_fb_status_poll < 2.0:
            return
        self._last_fb_status_poll = now
        self.db.set_setting("facebook_connection_status", self.fb.connection_status())
        if self.fb.browser_backend:
            self.db.set_setting("facebook_browser_backend", self.fb.browser_backend)

    def _schedule_due_facebook_campaigns(self):
        now = datetime.now().replace(microsecond=0).isoformat()
        for camp in self.db.due_campaigns(now):
            try:
                self._create_facebook_campaign_queue(camp)
            finally:
                self.db.bump_campaign(camp["id"])

    def _schedule_due_whatsapp_campaigns(self):
        now = datetime.now().replace(microsecond=0).isoformat()
        for camp in self.db.due_wa_campaigns(now):
            try:
                self._create_whatsapp_campaign_queue(camp)
            finally:
                self.db.bump_wa_campaign(camp["id"])

    def _create_facebook_campaign_queue(self, camp):
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

    def _create_whatsapp_campaign_queue(self, camp):
        contacts = self.db.list_wa_contacts(
            enabled_only=True,
            opted_in_only=True,
            keyword=camp["target_keyword"] or None,
        )
        if not contacts:
            self.db.audit("WARNING", "wa_campaign_no_contacts", camp["name"])
            return
        count, batches = self.db.enqueue_wa(
            camp["id"],
            [c["id"] for c in contacts],
            int(camp["batch_size"]),
            int(camp["interval_seconds"]),
        )
        self.db.audit("INFO", "wa_campaign_queued", f"{camp['name']}: {count} contacts; {batches} batches")

    def _process_due_facebook_queue(self):
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

    def _process_due_whatsapp_queue(self):
        item = self.db.next_due_wa_queue_item(datetime.now().replace(microsecond=0).isoformat())
        if not item:
            return
        try:
            mode = item["message_mode"] or "text"
            if mode == "template":
                self.wa.send_template(item["contact_phone"], item["template_name"] or "", item["template_language"] or "ar")
            else:
                self.wa.send_text(item["contact_phone"], item["message_text"] or "")
            self.db.mark_wa_queue(item["id"], "done")
            self.db.audit("INFO", "wa_message_done", f"{item['contact_name']} / batch {item['batch_no']}")
        except WhatsAppNotConfigured as exc:
            self.db.mark_wa_queue(item["id"], "failed", str(exc))
            self.db.audit("WARNING", "wa_not_configured", item["campaign_name"] or "")
        except WhatsAppError as exc:
            self.db.mark_wa_queue(item["id"], "failed", str(exc))
            self.db.audit("ERROR", "wa_message_failed", f"{item['contact_name']}: {exc}")
        except Exception as exc:
            self.db.mark_wa_queue(item["id"], "failed", repr(exc))
            self.db.audit("ERROR", "wa_message_failed", f"{item['contact_name']}: {repr(exc)}")
