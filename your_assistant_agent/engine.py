from __future__ import annotations

import queue
import threading
import time
from datetime import datetime
from typing import Any

from .db import Database
from .facebook import CheckpointDetected, FacebookAutomation, FacebookConfig, FacebookError, LoginRequired, ManualLoginInProgress
from .security import SecurityManager
from .telegram_remote import TelegramRemote
from .whatsapp import WhatsAppBusinessClient, WhatsAppError, WhatsAppNotConfigured
from .wake_support import schedule_windows_wake, send_magic_packet


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
        self.telegram = TelegramRemote(db, security, self.command)
        self._last_fb_status_poll = 0.0
        self._last_wake_refresh = 0.0
        self._last_wake_target = ""

    def command(self, name: str, payload=None):
        self.commands.put((name, payload))

    def shutdown(self):
        self.stop_event.set()
        self.command("shutdown")

    def run(self):
        self.db.audit("INFO", "engine_started")
        if not self.telegram.is_alive():
            self.telegram.start()
        while not self.stop_event.is_set():
            try:
                self._handle_commands()
                self._poll_facebook_status()
                self._refresh_auto_wake_schedule()
                if not self.db.get_setting("paused", False):
                    self._schedule_due_smart_rules()
                    self._schedule_due_facebook_campaigns()
                    self._schedule_due_whatsapp_campaigns()
                    self._process_due_smart_queue()
                    self._process_due_facebook_queue()
                    self._process_due_whatsapp_queue()
            except Exception as exc:
                self.db.audit("ERROR", "engine_loop_error", repr(exc))
            self.stop_event.wait(1.0)
        try:
            self.telegram.shutdown()
            self.telegram.join(timeout=3)
        except Exception:
            pass
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
            if name == "pause":
                self.db.set_setting("paused", True)
                self.db.audit("INFO", "agent_paused_remote")
                continue
            if name == "resume":
                self.db.set_setting("paused", False)
                self.db.audit("INFO", "agent_resumed_remote")
                continue
            if name == "emergency_stop":
                self.db.set_setting("paused", True)
                self.db.clear_pending()
                self.db.audit("SECURITY", "emergency_stop", "remote_or_ui")
                continue
            if name == "open_login":
                try:
                    backend = self.fb.open_manual_login()
                    self.db.set_setting("facebook_browser_backend", backend)
                    self.db.set_setting("facebook_connection_status", "manual_login")
                    self.db.set_setting("facebook_manual_login_started_at", time.time())
                    self.db.set_setting("facebook_browser_last_error", "")
                    self.db.audit("INFO", "facebook_manual_login_opened", backend)
                except Exception as exc:
                    self.db.set_setting("facebook_connection_status", "browser_error")
                    self.db.set_setting("facebook_browser_last_error", str(exc))
                    self.db.audit("ERROR", "facebook_browser_error", str(exc))
            elif name == "check_facebook_connection":
                self.db.set_setting("facebook_connection_status", "checking")
                self.db.set_setting("facebook_browser_last_error", "")
                try:
                    status = self.fb.verify_saved_session()
                    self.db.set_setting("facebook_connection_status", status)
                    self.db.set_setting("facebook_browser_backend", self.fb.browser_backend)
                    self.db.set_setting("facebook_manual_login_started_at", 0)
                    self.db.audit("INFO", "facebook_connection_checked", status)
                except ManualLoginInProgress as exc:
                    self.db.set_setting("facebook_connection_status", "profile_in_use")
                    self.db.set_setting("facebook_browser_last_error", str(exc))
                    self.db.audit("WARNING", "facebook_profile_in_use", str(exc))
                except CheckpointDetected as exc:
                    self.db.set_setting("facebook_connection_status", "verification_required")
                    self.db.set_setting("facebook_browser_last_error", str(exc))
                    self.db.audit("SECURITY", "facebook_checkpoint", str(exc))
                except Exception as exc:
                    self.db.set_setting("facebook_connection_status", "browser_error")
                    self.db.set_setting("facebook_browser_last_error", str(exc))
                    self.db.audit("ERROR", "facebook_connection_check_failed", str(exc))
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
            elif name == "discover_groups":
                self._discover_groups()
            elif name == "run_smart_rule_now":
                try:
                    rule = self.db.get_smart_rule(int(payload))
                    if rule:
                        created = self._create_smart_rule_queue(rule)
                        if created and rule["post_mode"] == "rotation":
                            self.db.advance_smart_rotation(rule["id"])
                except Exception as exc:
                    self.db.audit("ERROR", "smart_rule_manual_error", str(exc))
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
            elif name == "refresh_wake_schedule":
                self._last_wake_target = ""
                self._refresh_auto_wake_schedule(force=True)
            elif name == "send_wol":
                try:
                    mac = str(self.db.get_setting("wol_target_mac", "") or "")
                    broadcast = str(self.db.get_setting("wol_broadcast_ip", "255.255.255.255") or "255.255.255.255")
                    port = int(self.db.get_setting("wol_port", 9) or 9)
                    send_magic_packet(mac, broadcast, port)
                    self.db.set_setting("wol_last_result", {"ok": True, "message": f"Magic packet sent to {mac}"})
                    self.db.audit("INFO", "wol_packet_sent", f"{mac} via {broadcast}:{port}")
                except Exception as exc:
                    self.db.set_setting("wol_last_result", {"ok": False, "message": str(exc)})
                    self.db.audit("ERROR", "wol_packet_failed", str(exc))
            elif name == "telegram_test":
                ok, message = self.telegram.send_test()
                self.db.set_setting("telegram_test_status", {"ok": ok, "message": message, "ts": time.time()})
                self.db.audit("INFO" if ok else "ERROR", "telegram_test", message)

    def _poll_facebook_status(self):
        now = time.monotonic()
        if now - self._last_fb_status_poll < 2.0:
            return
        self._last_fb_status_poll = now
        if not self.fb.is_open():
            return
        self.db.set_setting("facebook_connection_status", self.fb.connection_status())
        if self.fb.browser_backend:
            self.db.set_setting("facebook_browser_backend", self.fb.browser_backend)

    def _refresh_auto_wake_schedule(self, force: bool = False):
        now = time.time()
        if not force and now - self._last_wake_refresh < 30:
            return
        self._last_wake_refresh = now
        if not bool(self.db.get_setting("auto_wake_for_smart_rules", False)):
            return
        target_iso = self.db.next_smart_rule_time()
        if not target_iso or (target_iso == self._last_wake_target and not force):
            return
        try:
            target = datetime.fromisoformat(target_iso)
            minutes = int(self.db.get_setting("wake_minutes_early", 2) or 2)
            ok, message = schedule_windows_wake(target, minutes_early=minutes)
            self.db.set_setting("wake_schedule_status", {"ok": ok, "message": message, "target": target_iso})
            self.db.audit("INFO" if ok else "WARNING", "wake_schedule_updated", f"{target_iso}: {message}")
            if ok:
                self._last_wake_target = target_iso
        except Exception as exc:
            self.db.set_setting("wake_schedule_status", {"ok": False, "message": str(exc), "target": target_iso})
            self.db.audit("ERROR", "wake_schedule_failed", str(exc))

    def _discover_groups(self):
        self.db.set_setting("facebook_group_discovery_result", {
            "status": "running", "count": 0, "ts": time.time(), "error": ""
        })
        self.db.audit("INFO", "groups_discovery_started", self.fb.browser_backend or "")
        try:
            groups = self.fb.discover_joined_groups(limit=300)
            count = self.db.upsert_discovered_groups(groups)
            status = "done" if count else "empty"
            self.db.set_setting("facebook_group_discovery_result", {
                "status": status, "count": count, "ts": time.time(), "error": ""
            })
            if count:
                self.db.audit("INFO", "groups_discovery_done", str(count))
            else:
                self.db.audit("WARNING", "groups_discovery_empty", "0")
        except ManualLoginInProgress as exc:
            self.db.set_setting("facebook_group_discovery_result", {
                "status": "profile_in_use", "count": 0, "ts": time.time(), "error": str(exc)
            })
            self.db.audit("WARNING", "groups_discovery_failed", str(exc))
        except LoginRequired as exc:
            self.db.set_setting("facebook_group_discovery_result", {
                "status": "login_required", "count": 0, "ts": time.time(), "error": str(exc)
            })
            self.db.audit("WARNING", "facebook_login_required", "group_discovery")
        except CheckpointDetected as exc:
            self.db.set_setting("paused", True)
            self.db.set_setting("facebook_group_discovery_result", {
                "status": "checkpoint", "count": 0, "ts": time.time(), "error": str(exc)
            })
            self.db.audit("SECURITY", "facebook_checkpoint", str(exc))
        except Exception as exc:
            self.db.set_setting("facebook_group_discovery_result", {
                "status": "error", "count": 0, "ts": time.time(), "error": str(exc)
            })
            self.db.audit("ERROR", "groups_discovery_failed", str(exc))
        finally:
            # Discovery is a finite operation. Close only the agent's automation
            # context afterwards so the dedicated profile is released cleanly.
            try:
                self.fb.stop()
            except Exception:
                pass

    def _schedule_due_smart_rules(self):
        now = datetime.now().replace(microsecond=0).isoformat()
        for rule in self.db.due_smart_rules(now):
            created = False
            try:
                created = self._create_smart_rule_queue(rule)
            finally:
                self.db.bump_smart_rule(rule["id"], advance_rotation=bool(created and rule["post_mode"] == "rotation"))

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

    def _create_smart_rule_queue(self, rule) -> bool:
        self.db.audit("INFO", "smart_rule_start", rule["name"])
        groups = self.db.list_groups(
            enabled_only=True,
            keyword=rule["group_keyword"] or None,
            limit=int(rule["max_groups"]),
        )
        if not groups:
            self.db.audit("WARNING", "smart_rule_no_groups", rule["name"])
            return False
        try:
            self.fb.ensure_logged_in()
            wanted = max(12, int(rule["rotation_offset"] or 0) + 4, int(rule["post_offset"] or 0) + 4)
            posts = self.fb.find_recent_post_urls(rule["source_page_url"], limit=min(wanted, 50))
        except LoginRequired:
            self.db.audit("WARNING", "facebook_login_required", rule["name"])
            return False
        except CheckpointDetected as exc:
            self.db.set_setting("paused", True)
            self.db.audit("SECURITY", "facebook_checkpoint", str(exc))
            return False
        except Exception as exc:
            self.db.audit("ERROR", "smart_post_discovery_failed", f"{rule['name']}: {exc}")
            return False
        if not posts:
            self.db.audit("ERROR", "smart_post_discovery_failed", f"{rule['name']}: no posts found")
            return False
        if rule["post_mode"] == "rotation":
            offset = int(rule["rotation_offset"] or 0) % len(posts)
        else:
            offset = int(rule["post_offset"] or 0)
            if offset >= len(posts):
                self.db.audit("ERROR", "smart_post_offset_missing", f"{rule['name']}: found {len(posts)}, offset={offset}")
                return False
        post_url = posts[offset]
        eligible = []
        skipped = 0
        for g in groups:
            if self.db.was_shared_recently(g["id"], post_url, int(rule["no_repeat_days"] or 0)):
                skipped += 1
                continue
            eligible.append(g)
        if not eligible:
            self.db.audit("INFO", "smart_rule_all_deduped", f"{rule['name']}: {skipped} skipped")
            return False
        count = self.db.enqueue_smart(rule["id"], [g["id"] for g in eligible], post_url, int(rule["interval_seconds"]))
        self.db.audit("INFO", "smart_rule_queued", f"{rule['name']}: {count} groups; skipped={skipped}; source={post_url}")
        return bool(count)

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

    def _process_due_smart_queue(self):
        item = self.db.next_due_smart_queue_item(datetime.now().replace(microsecond=0).isoformat())
        if not item:
            return
        try:
            self.fb.ensure_logged_in()
            if (item["share_mode"] or "native_share") == "native_share":
                self.fb.share_post_to_group(
                    group_name=item["group_name"],
                    group_url=item["group_url"],
                    post_url=item["post_url"],
                )
            else:
                self.fb.post_link_to_group(item["group_url"], item["post_url"], "")
            self.db.mark_smart_queue(item["id"], "done")
            self.db.record_share(item["rule_id"], item["group_id"], item["post_url"], "done")
            self.db.audit("INFO", "smart_group_share_done", f"{item['rule_name']}: {item['group_name']}")
        except LoginRequired as exc:
            self.db.mark_smart_queue(item["id"], "failed", str(exc))
            self.db.record_share(item["rule_id"], item["group_id"], item["post_url"], "failed", str(exc))
            self.db.set_setting("paused", True)
            self.db.audit("WARNING", "facebook_login_required", item["group_name"])
        except CheckpointDetected as exc:
            self.db.mark_smart_queue(item["id"], "blocked", str(exc))
            self.db.record_share(item["rule_id"], item["group_id"], item["post_url"], "blocked", str(exc))
            self.db.set_setting("paused", True)
            self.db.audit("SECURITY", "facebook_checkpoint", item["group_name"])
        except FacebookError as exc:
            self.db.mark_smart_queue(item["id"], "failed", str(exc))
            self.db.record_share(item["rule_id"], item["group_id"], item["post_url"], "failed", str(exc))
            self.db.audit("ERROR", "smart_group_share_failed", f"{item['group_name']}: {exc}")
        except Exception as exc:
            self.db.mark_smart_queue(item["id"], "failed", repr(exc))
            self.db.record_share(item["rule_id"], item["group_id"], item["post_url"], "failed", repr(exc))
            self.db.audit("ERROR", "smart_group_share_failed", f"{item['group_name']}: {repr(exc)}")

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
