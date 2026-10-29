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

    def __init__(self, db: ChatDB, settings: Settings, activity: Callable[[str, str], None] | None = None, browser_bridge=None):
        self.db = db
        self.settings = settings
        self.activity = activity or (lambda kind, detail: self.db.add_activity(kind, detail))
        self.browser_bridge = browser_bridge
        self._fb = None
        self._fb_lock = threading.RLock()
        self._exec_lock = threading.Lock()
        self._stop_event = threading.Event()
        self._task_cancel_event = threading.Event()
        self._task_pause_event = threading.Event()
        self._scheduler: threading.Thread | None = None
        self._last_status = "not_checked"
        self._last_backend = ""
        self._active_rule_id: int | None = None
        self._current_step = "idle"
        self._progress_done = 0
        self._progress_total = 0
        self._started_at: float | None = None

    def current_status(self) -> dict:
        return {
            "facebook": self.status_text(),
            "active_rule_id": self._active_rule_id,
            "step": self._current_step,
            "done": self._progress_done,
            "total": self._progress_total,
            "paused": self._task_pause_event.is_set(),
            "running": self._active_rule_id is not None,
            "started_at": self._started_at,
        }

    def pause_current(self) -> bool:
        if self._active_rule_id is None:
            return False
        self._task_pause_event.set()
        self.activity("facebook_rule_paused", f"id={self._active_rule_id}")
        return True

    def resume_current(self) -> bool:
        if self._active_rule_id is None:
            return False
        self._task_pause_event.clear()
        self.activity("facebook_rule_resumed", f"id={self._active_rule_id}")
        return True

    def stop_current(self) -> bool:
        if self._active_rule_id is None:
            return False
        self._task_cancel_event.set()
        self._task_pause_event.clear()
        self.activity("facebook_rule_stop_requested", f"id={self._active_rule_id}")
        return True

    def _wait_if_paused(self) -> bool:
        while self._task_pause_event.is_set() and not self._task_cancel_event.is_set() and not self._stop_event.is_set():
            time.sleep(0.25)
        return not (self._task_cancel_event.is_set() or self._stop_event.is_set())

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

        locale = "ar-JO" if self.settings.interface_language != "en" else "en-US"
        choice = (self.settings.facebook_browser_choice or "auto").lower()
        resolved = "auto"
        label = ""
        if choice == "custom" and self.settings.facebook_browser_custom_path:
            resolved = self.settings.facebook_browser_custom_path
            label = "Custom browser"
        elif choice in {"edge", "chrome"}:
            try:
                from ..facebook_backend.browser_discovery import discover_installed_browsers
                needle = "edge" if choice == "edge" else "chrome"
                match = next((b for b in discover_installed_browsers() if needle in (b.name + " " + b.executable.name).casefold()), None)
                if match:
                    resolved = str(match.executable); label = match.name
            except Exception:
                pass
        # 'default' and Firefox are handled by the normal-browser extension.
        # Managed automation deliberately falls back to a supported Chromium browser.
        return FacebookAutomation(FacebookConfig(locale=locale, browser_choice=resolved, browser_label=label))

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

    def _t(self, ar_text: str, en_text: str) -> str:
        return ar_text if self.settings.interface_language == "ar" else en_text

    def status_code(self) -> str:
        """Stable machine-readable connection state for UI logic."""
        return self._last_status

    def status_text(self) -> str:
        ar = self.settings.interface_language == "ar"
        labels = {
            "not_checked": ("لم يتم الفحص","Not checked"),
            "connected": ("متصل","Connected"),
            "not_connected": ("غير متصل","Not connected"),
            "browser_not_connected": ("المتصفح غير مربوط","Browser not connected"),
            "manual_login": ("بانتظار تسجيل الدخول","Waiting for login"),
            "error": ("خطأ","Error"),
        }
        pair = labels.get(self._last_status, (self._last_status, self._last_status))
        text = pair[0] if ar else pair[1]
        return text + (f" — {self._last_backend}" if self._last_backend else "")

    def open_manual_login(self) -> FacebookActionResult:
        # Primary path: the user's already-open normal browser through the local
        # extension. Fallback: managed visible browser profile. CAPTCHA/login
        # themselves remain manual in both paths.
        if self.settings.facebook_browser_mode == "extension_first" and self.browser_bridge and self.browser_bridge.connected:
            try:
                result = self.browser_bridge.execute("open_url", url="https://www.facebook.com/", active=True, timeout=8)
                if result.get("ok"):
                    self._last_status = "manual_login"
                    self._last_backend = "normal-browser-extension"
                    self.activity("facebook_manual_login", self._last_backend)
                    return FacebookActionResult(True, self._t("تم فتح Facebook في المتصفح العادي. سجل الدخول يدويًا إذا لزم، ثم اضغط فحص الاتصال.", "Facebook opened in your normal browser. Sign in manually if needed, then click Check connection."))
            except Exception as exc:
                self.activity("browser_extension_fallback", f"login: {type(exc).__name__}: {exc}")
        try:
            backend = self.fb().open_manual_login()
            self._last_status = "manual_login"
            self._last_backend = backend
            self.activity("facebook_manual_login", backend)
            return FacebookActionResult(True, self._t(f"تم فتح Facebook في {backend}. سجل الدخول يدويًا ثم أغلق نافذة المتصفح واضغط فحص الاتصال.", f"Facebook opened in {backend}. Sign in manually, close that browser window, then click Check connection."))
        except Exception as exc:
            self._last_status = "error"
            self.activity("facebook_login_error", f"{type(exc).__name__}: {exc}")
            return FacebookActionResult(False, self._t(f"تعذر فتح تسجيل الدخول: {exc}", f"Could not open login: {exc}"))

    def _verify_via_open_browser(self) -> FacebookActionResult | None:
        if not (self.browser_bridge and self.browser_bridge.connected):
            return None
        try:
            result = self.browser_bridge.execute("facebook_session", timeout=12)
            state = str(result.get("status") or "unknown")
            connected = bool(result.get("ok")) and state == "connected"
            self._last_status = "connected" if connected else "not_connected" if state == "not_connected" else "error"
            self._last_backend = "normal-browser-extension"
            self.activity("facebook_connection" if connected else "facebook_connection_error", f"{state}; {self._last_backend}")
            if connected:
                return FacebookActionResult(True, "Facebook: connected — normal-browser-extension")
            if state == "checkpoint":
                return FacebookActionResult(False, self._t("Facebook يطلب تحققًا أمنيًا. افتحه وأكمل التحقق يدويًا.", "Facebook requires a security check. Open Facebook and complete it manually."))
            if state == "not_connected":
                return FacebookActionResult(False, self._t("حساب Facebook غير مسجل الدخول في المتصفح العادي.", "Facebook is not signed in in the normal browser."))
            return FacebookActionResult(False, self._t("إضافة المتصفح متصلة، لكن لم نتمكن من التحقق من جلسة Facebook. افتح Facebook ثم أعد الفحص.", "The browser extension is connected, but the Facebook session could not be verified. Open Facebook and check again."))
        except Exception as exc:
            self.activity("browser_extension_fallback", f"verify: {type(exc).__name__}: {exc}")
            return None

    def verify_session_background(self) -> FacebookActionResult:
        result = self._verify_via_open_browser()
        if result is not None:
            return result
        # Never pop up a managed automation browser merely because the app opened.
        self._last_status = "browser_not_connected"
        self._last_backend = ""
        self.activity("facebook_connection_deferred", "normal browser extension not connected; manual check available")
        return FacebookActionResult(False, "Facebook: browser bridge not connected")

    def verify_session(self) -> FacebookActionResult:
        ext = self._verify_via_open_browser() if self.settings.facebook_browser_mode == "extension_first" else None
        if ext is not None:
            return ext
        try:
            status = self.fb().verify_saved_session()
            self._last_status = status
            self._last_backend = getattr(self.fb(), "browser_backend", "") or self._last_backend
            self.activity("facebook_connection", f"{status}; {self._last_backend}")
            return FacebookActionResult(status == "connected", f"Facebook: {status}" + (f" — {self._last_backend}" if self._last_backend else ""))
        except Exception as exc:
            self._last_status = "error"
            self.activity("facebook_connection_error", f"{type(exc).__name__}: {exc}")
            return FacebookActionResult(False, self._t(f"فشل فحص جلسة Facebook: {exc}", f"Facebook session check failed: {exc}"))
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
            return FacebookActionResult(True, self._t(f"تم التعرف على {count} مجموعة وحفظها.", f"Discovered and saved {count} groups."), count=count)
        except Exception as exc:
            self.activity("facebook_group_discovery_error", f"{type(exc).__name__}: {exc}")
            return FacebookActionResult(False, self._t(f"تعذر اكتشاف المجموعات: {exc}", f"Could not discover groups: {exc}"))
        finally:
            self.close_browser()

    def save_rule(self, plan) -> FacebookActionResult:
        try:
            rule_id = self.db.add_rule(plan)
            count = self.db.count_groups(getattr(plan, "group_keyword", ""))
            self.activity("smart_rule_saved", f"id={rule_id}; groups={count}; {plan.name}")
            return FacebookActionResult(True, self._t(f"تم حفظ المهمة رقم {rule_id}. عدد المجموعات المطابقة حاليًا: {count}.", f"Saved task #{rule_id}. Currently matching groups: {count}."), count=count)
        except Exception as exc:
            self.activity("smart_rule_save_error", f"{type(exc).__name__}: {exc}")
            return FacebookActionResult(False, self._t(f"تعذر حفظ المهمة: {exc}", f"Could not save task: {exc}"))

    def run_rule_now(self, rule_id: int) -> FacebookActionResult:
        rule = self.db.get_rule(rule_id)
        if not rule:
            return FacebookActionResult(False, self._t("المهمة غير موجودة.", "Task not found."))
        threading.Thread(
            target=self._execute_rule_guarded,
            args=(rule,),
            daemon=True,
            name=f"yaa-facebook-now-{rule_id}",
        ).start()
        return FacebookActionResult(True, self._t(f"بدأ تنفيذ المهمة {rule_id} في الخلفية.", f"Task {rule_id} started in the background."))

    def _execute_rule_guarded(self, rule: dict) -> None:
        if not self._exec_lock.acquire(blocking=False):
            self.activity("facebook_rule_delayed", f"id={rule.get('id')}; another Facebook task is active")
            return
        self._task_cancel_event.clear()
        self._task_pause_event.clear()
        self._active_rule_id = int(rule.get("id") or 0) or None
        self._current_step = "starting"
        self._progress_done = 0
        self._progress_total = 0
        self._started_at = time.time()
        try:
            self._execute_rule(rule)
        finally:
            self._active_rule_id = None
            self._current_step = "idle"
            self._progress_done = 0
            self._progress_total = 0
            self._started_at = None
            self._task_cancel_event.clear()
            self._task_pause_event.clear()
            self._exec_lock.release()
            self.close_browser()

    def _execute_rule(self, rule: dict) -> None:
        rule_id = int(rule["id"])
        groups = self.db.list_groups(keyword=rule.get("group_keyword") or "", limit=int(rule.get("max_groups") or 100))
        if not groups:
            self.activity("facebook_rule_no_groups", f"id={rule_id}; keyword={rule.get('group_keyword','')}")
            return
        self._progress_total = len(groups)
        self._current_step = "opening_facebook"
        self.activity("facebook_rule_start", f"id={rule_id}; groups={len(groups)}; keyword={rule.get('group_keyword','')}")
        try:
            self.activity("facebook_opening", f"id={rule_id}; opening saved browser session")
            fb = self.fb()
            fb.ensure_logged_in()
            wanted = max(8, int(rule.get("post_offset") or 0) + 4)
            self._current_step = "finding_source_post"
            self.activity("facebook_source_post_search", f"id={rule_id}; page={rule.get('source_page_url','')}; wanted={wanted}")
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
            self._current_step = "sharing"
            self.activity("facebook_post_found", f"id={rule_id}; post={post_url}")

            submitted = 0
            skipped = 0
            interval = max(30, int(rule.get("interval_seconds") or 60))
            no_repeat = max(0, int(rule.get("no_repeat_days") or 14))
            for index, group in enumerate(groups):
                if not self._wait_if_paused():
                    self.activity("facebook_rule_cancelled", f"id={rule_id}; done={self._progress_done}/{self._progress_total}")
                    break
                gid = int(group["id"])
                if self.db.was_shared_recently(gid, post_url, no_repeat):
                    skipped += 1
                    continue
                try:
                    self._progress_done = index
                    self.activity("facebook_group_share_start", f"{index + 1}/{len(groups)}; {group['name']}")
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
            self.activity("facebook_rule_done", f"id={rule_id}; total={len(groups)}; submitted={submitted}; skipped={skipped}")
        except Exception as exc:
            self.activity("facebook_rule_error", f"id={rule_id}; {type(exc).__name__}: {exc}")
