from __future__ import annotations

import threading
import time
from dataclasses import dataclass
from datetime import datetime
from typing import Callable

from ..config import Settings
from ..storage.db import ChatDB


@dataclass
class FacebookActionResult:
    ok: bool
    message: str
    count: int = 0


class FacebookService:
    """Lazy Facebook automation + scheduler used by the Smart Agent.

    Playwright and the browser backend are imported only when a Facebook action
    is actually requested. The scheduler itself stays tiny and merely checks
    SQLite timestamps, so keeping the app open does not load a browser or model.
    """

    def __init__(self, db: ChatDB, settings: Settings, activity: Callable[[str, str], None] | None = None):
        self.db = db
        self.settings = settings
        self.activity = activity or (lambda kind, detail: self.db.add_activity(kind, detail))
        self._fb = None
        self._fb_lock = threading.RLock()
        self._exec_lock = threading.Lock()
        self._stop_event = threading.Event()
        self._scheduler: threading.Thread | None = None
        self._last_status = "not_checked"
        self._last_backend = ""

    def update_settings(self, settings: Settings) -> None:
        changed_browser = settings.facebook_browser_choice != self.settings.facebook_browser_choice
        self.settings = settings
        if changed_browser:
            self.close_browser()

    def start_scheduler(self) -> None:
        if self._scheduler and self._scheduler.is_alive():
            return
        self._stop_event.clear()
        self._scheduler = threading.Thread(target=self._scheduler_loop, daemon=True, name="yaa-smart-scheduler")
        self._scheduler.start()

    def shutdown(self) -> None:
        self._stop_event.set()
        self.close_browser()

    def _scheduler_loop(self) -> None:
        while not self._stop_event.wait(2.0):
            if not self.settings.smart_agent_enabled:
                continue
            try:
                due = self.db.due_rules(datetime.now().replace(microsecond=0).isoformat())
                for rule in due:
                    if not rule:
                        continue
                    self.db.advance_rule(int(rule["id"]))
                    threading.Thread(
                        target=self._execute_rule_guarded,
                        args=(rule,),
                        daemon=True,
                        name=f"yaa-facebook-rule-{rule['id']}",
                    ).start()
            except Exception as exc:
                self.activity("scheduler_error", f"{type(exc).__name__}: {exc}")

    def _make_fb(self):
        # Lazy import is deliberate: importing Playwright is unnecessary for a
        # normal chat-only session.
        from ..facebook_backend.facebook import FacebookAutomation, FacebookConfig

        locale = "ar-JO" if self.settings.selected_agent == "arabic" else "en-US"
        return FacebookAutomation(FacebookConfig(
            locale=locale,
            browser_choice=self.settings.facebook_browser_choice or "auto",
        ))

    def fb(self):
        with self._fb_lock:
            if self._fb is None:
                self._fb = self._make_fb()
            return self._fb

    def close_browser(self) -> None:
        with self._fb_lock:
            fb, self._fb = self._fb, None
        if fb is not None:
            try:
                fb.stop()
            except Exception:
                pass

    def status_text(self) -> str:
        return f"{self._last_status}" + (f" — {self._last_backend}" if self._last_backend else "")

    def open_manual_login(self) -> FacebookActionResult:
        try:
            backend = self.fb().open_manual_login()
            self._last_status = "manual_login"
            self._last_backend = backend
            self.activity("facebook_manual_login", backend)
            return FacebookActionResult(True, f"تم فتح Facebook في {backend}. سجل الدخول يدويًا ثم أغلق نافذة المتصفح واضغط فحص الاتصال.")
        except Exception as exc:
            self._last_status = "error"
            self.activity("facebook_login_error", f"{type(exc).__name__}: {exc}")
            return FacebookActionResult(False, f"تعذر فتح تسجيل الدخول: {exc}")

    def verify_session(self) -> FacebookActionResult:
        try:
            status = self.fb().verify_saved_session()
            self._last_status = status
            self._last_backend = getattr(self.fb(), "browser_backend", "") or self._last_backend
            self.activity("facebook_connection", f"{status}; {self._last_backend}")
            return FacebookActionResult(status == "connected", f"Facebook: {status}" + (f" — {self._last_backend}" if self._last_backend else ""))
        except Exception as exc:
            self._last_status = "error"
            self.activity("facebook_connection_error", f"{type(exc).__name__}: {exc}")
            return FacebookActionResult(False, f"فشل فحص جلسة Facebook: {exc}")
        finally:
            self.close_browser()

    def discover_groups(self, limit: int = 500) -> FacebookActionResult:
        try:
            fb = self.fb()
            fb.ensure_logged_in()
            groups = fb.discover_joined_groups(limit=max(1, min(int(limit), 1000)))
            count = self.db.upsert_groups(groups)
            self._last_status = "connected"
            self._last_backend = getattr(fb, "browser_backend", "") or self._last_backend
            self.activity("facebook_groups_discovered", f"saved={count}")
            return FacebookActionResult(True, f"تم التعرف على {count} مجموعة وحفظها.", count=count)
        except Exception as exc:
            self.activity("facebook_group_discovery_error", f"{type(exc).__name__}: {exc}")
            return FacebookActionResult(False, f"تعذر اكتشاف المجموعات: {exc}")
        finally:
            self.close_browser()

    def save_rule(self, plan) -> FacebookActionResult:
        try:
            rule_id = self.db.add_rule(plan)
            count = self.db.count_groups(getattr(plan, "group_keyword", ""))
            self.activity("smart_rule_saved", f"id={rule_id}; groups={count}; {plan.name}")
            return FacebookActionResult(True, f"تم حفظ المهمة رقم {rule_id}. عدد المجموعات المطابقة حاليًا: {count}.", count=count)
        except Exception as exc:
            self.activity("smart_rule_save_error", f"{type(exc).__name__}: {exc}")
            return FacebookActionResult(False, f"تعذر حفظ المهمة: {exc}")

    def run_rule_now(self, rule_id: int) -> FacebookActionResult:
        rule = self.db.get_rule(rule_id)
        if not rule:
            return FacebookActionResult(False, "المهمة غير موجودة.")
        threading.Thread(
            target=self._execute_rule_guarded,
            args=(rule,),
            daemon=True,
            name=f"yaa-facebook-now-{rule_id}",
        ).start()
        return FacebookActionResult(True, f"بدأ تنفيذ المهمة {rule_id} في الخلفية.")

    def _execute_rule_guarded(self, rule: dict) -> None:
        if not self._exec_lock.acquire(blocking=False):
            self.activity("facebook_rule_delayed", f"id={rule.get('id')}; another Facebook task is active")
            return
        try:
            self._execute_rule(rule)
        finally:
            self._exec_lock.release()
            self.close_browser()

    def _execute_rule(self, rule: dict) -> None:
        rule_id = int(rule["id"])
        groups = self.db.list_groups(keyword=rule.get("group_keyword") or "", limit=int(rule.get("max_groups") or 100))
        if not groups:
            self.activity("facebook_rule_no_groups", f"id={rule_id}; keyword={rule.get('group_keyword','')}")
            return
        self.activity("facebook_rule_start", f"id={rule_id}; groups={len(groups)}")
        try:
            fb = self.fb()
            fb.ensure_logged_in()
            wanted = max(8, int(rule.get("post_offset") or 0) + 4)
            posts = fb.find_recent_post_urls(str(rule.get("source_page_url") or ""), limit=min(wanted, 50))
            if not posts:
                self.activity("facebook_rule_error", f"id={rule_id}; no source posts found")
                return
            offset = int(rule.get("post_offset") or 0)
            if rule.get("post_mode") == "rotation":
                offset = 0
            if offset >= len(posts):
                self.activity("facebook_rule_error", f"id={rule_id}; post offset {offset}, found {len(posts)}")
                return
            post_url = posts[offset]

            submitted = 0
            skipped = 0
            interval = max(30, int(rule.get("interval_seconds") or 60))
            no_repeat = max(0, int(rule.get("no_repeat_days") or 14))
            for index, group in enumerate(groups):
                if self._stop_event.is_set():
                    break
                gid = int(group["id"])
                if self.db.was_shared_recently(gid, post_url, no_repeat):
                    skipped += 1
                    continue
                try:
                    outcome = fb.share_post_to_group(
                        group_name=group["name"],
                        group_url=group["url"],
                        post_url=post_url,
                    )
                    outcome = outcome if outcome in {"published", "submitted", "pending_approval"} else "submitted"
                    self.db.record_share(rule_id, gid, post_url, outcome)
                    submitted += 1
                    self.activity("facebook_share", f"{group['name']}: {outcome}")
                except Exception as exc:
                    self.db.record_share(rule_id, gid, post_url, "failed", str(exc))
                    self.activity("facebook_share_error", f"{group['name']}: {type(exc).__name__}: {exc}")
                if index < len(groups) - 1 and not self._stop_event.wait(interval):
                    continue
            self.activity("facebook_rule_done", f"id={rule_id}; submitted={submitted}; skipped={skipped}")
        except Exception as exc:
            self.activity("facebook_rule_error", f"id={rule_id}; {type(exc).__name__}: {exc}")
