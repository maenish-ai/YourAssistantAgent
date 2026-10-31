from __future__ import annotations

import threading
import time
from dataclasses import dataclass
from functools import wraps
from datetime import datetime, timedelta, timezone
from urllib.parse import urlsplit
from typing import Callable

from ..config import Settings
from ..storage.db import ChatDB


@dataclass
class FacebookActionResult:
    ok: bool
    message: str
    count: int = 0


def _browser_action(method):
    @wraps(method)
    def execute(self,*args,**kwargs):
        if not self._exec_lock.acquire(blocking=False):
            return FacebookActionResult(False,self._t('هناك مهمة Facebook قيد التنفيذ؛ انتظر نتيجتها قبل تغيير الصفحة.','A Facebook task is running; wait for its result before navigating.'))
        try:return method(self,*args,**kwargs)
        finally:self._exec_lock.release()
    return execute


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
        self._interactive_browser = False
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
        self._result_lock = threading.RLock()
        self._rule_results: dict[int, dict] = {}
        self._completion_listeners: list[Callable[[int, dict], None]] = []

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

    def add_completion_listener(self, callback: Callable[[int, dict], None]) -> None:
        with self._result_lock:
            if callback not in self._completion_listeners:
                self._completion_listeners.append(callback)

    def remove_completion_listener(self, callback: Callable[[int, dict], None]) -> None:
        with self._result_lock:
            if callback in self._completion_listeners:
                self._completion_listeners.remove(callback)

    def rule_result(self, rule_id: int) -> dict | None:
        with self._result_lock:
            result = self._rule_results.get(int(rule_id))
            return dict(result) if result else None

    def _complete(self, rule_id: int, result: dict) -> None:
        with self._result_lock:
            self._rule_results[rule_id] = dict(result)
            # Bounded process-local result cache; history remains in SQLite.
            if len(self._rule_results) > 100:
                self._rule_results.pop(next(iter(self._rule_results)))
            listeners = list(self._completion_listeners)
        for callback in listeners:
            try:
                callback(rule_id, dict(result))
            except Exception:
                self.activity("facebook_result_delivery_error", f"id={rule_id}")

    @staticmethod
    def _facebook_url(value: str, *, group: bool = False) -> str:
        value = str(value or '').strip()
        parsed = urlsplit(value)
        host = (parsed.hostname or '').lower()
        if (parsed.scheme != 'https' or parsed.username or parsed.password or
                parsed.port not in (None, 443) or
                not (host == 'facebook.com' or host.endswith('.facebook.com')) or
                (group and not parsed.path.startswith('/groups/'))):
            raise ValueError('A valid HTTPS Facebook URL is required')
        return value

    def preview_campaign(self, source_page_url: str, group_keyword: str = '',
                         max_groups: int = 100, post_offset: int = 0,
                         post_count: int = 1) -> dict:
        """Resolve actual targets before approval, through the publishing profile."""
        source = self._facebook_url(source_page_url)
        count, offset = int(post_count), int(post_offset)
        if not 1 <= count <= 4 or not 0 <= offset <= 46:
            raise ValueError('Choose 1 to 4 posts and an offset from 0 to 46')
        if not self._exec_lock.acquire(blocking=False):
            raise RuntimeError('Another Facebook task is running; wait before preparing a preview')
        try:
            groups = self.db.list_groups(keyword=group_keyword, limit=max(1, min(int(max_groups), 500)), enabled_only=True)
            if not groups:
                raise ValueError('No matching saved groups. Refresh or change the group selection first')
            selected = [{'id': int(g['id']), 'name': str(g['name']),
                         'url': self._facebook_url(g['url'], group=True)} for g in groups]
            self._interactive_browser=True
            fb = self.fb()
            fb.ensure_logged_in()
            self._remember_status('connected',fb.browser_backend)
            candidates = fb.find_recent_post_urls(source, limit=min(50, max(8, offset + count)))
            posts = list(dict.fromkeys(self._facebook_url(u) for u in candidates))
            chosen = posts[offset:offset + count]
            if len(chosen) != count:
                raise ValueError(f'Requested {count} posts at offset {offset}, but only {len(chosen)} were found. Nothing was approved')
            self.activity('facebook_preview_ready', f'posts={len(chosen)}; groups={len(selected)}; managed publishing profile')
            return {'post_urls': chosen, 'selected_groups': selected, 'post_count': count,
                    'approval_snapshot': True}
        except Exception as exc:
            self._remember_failure(exc)
            raise
        finally:
            self._release_browser_after_action()
            self._exec_lock.release()

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
                from ..facebook_backend.session_worker import BrowserSession
                self._fb = BrowserSession(self._make_fb)
            return self._fb

    def _release_browser_after_action(self):
        if not self._interactive_browser:self.close_browser()

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

    def _remember_status(self, state: str, backend: str = '') -> None:
        self._last_status = {'not_connected': 'manual_login', 'browser_closed': 'browser_not_connected'}.get(state, state)
        self._last_backend = backend or self._last_backend

    def _remember_failure(self, exc: Exception) -> None:
        from ..facebook_backend.facebook import CheckpointDetected, LoginRequired
        if isinstance(exc, (ValueError, TypeError, OverflowError)):return
        if isinstance(exc, CheckpointDetected):self._last_status='verification_required'
        elif isinstance(exc, LoginRequired):self._last_status='manual_login'
        else:self._last_status='error'

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
            "verification_required": ("بانتظار تحقق فيسبوك","Waiting for Facebook verification"),
            "browser_closed": ("متصفح التحكم مغلق","Controlled browser closed"),
            "error": ("خطأ","Error"),
        }
        pair = labels.get(self._last_status, (self._last_status, self._last_status))
        text = pair[0] if ar else pair[1]
        return text + (f" — {self._last_backend}" if self._last_backend else "")

    @_browser_action
    def open_manual_login(self) -> FacebookActionResult:
        return self._open_manual_login_impl()

    def _open_manual_login_impl(self) -> FacebookActionResult:
        # All assistant page/post/publishing operations use this same controlled
        # profile. Opening the extension's ordinary profile here silently sent
        # later reads to a different, usually signed-out browser.
        try:
            self._interactive_browser=True
            browser=self.fb()
            if browser.supports('open_interactive'):
                state=browser.open_interactive();backend=browser.browser_backend
            else:
                backend=browser.open_manual_login();state='not_connected'
            self._remember_status(state, backend)
            if state not in {'connected','not_connected','manual_login','verification_required'}:
                return FacebookActionResult(False,self._t('متصفح التحكم لم يبق مفتوحاً. اطلب فتح Facebook مجدداً.','The controlled browser did not remain open. Request Facebook again.'))
            self.activity('facebook_opened',str(backend))
            text=self._t('فتحت Facebook والحساب مسجل الدخول؛ المتصفح جاهز للأوامر.','Opened Facebook; its signed-in account is ready for commands.') if state=='connected' else self._t(
                'فتحت Facebook في متصفح البرنامج. أكمل تسجيل الدخول إذا طُلب؛ اترك النافذة مفتوحة، وسأستخدم نفس الجلسة للجروبات والمنشورات.',
                'Opened Facebook in the app browser. Complete sign-in if requested; leave this window open. The same session is used for groups and posts.')
            return FacebookActionResult(True,text)
        except Exception as exc:
            self.activity('facebook_login_error',type(exc).__name__);self._remember_failure(exc)
            return FacebookActionResult(False,self._t('تعذر تشغيل متصفح التحكم: '+str(exc),'Could not start the controlled browser: '+str(exc)))

    def open_publishing_login(self) -> FacebookActionResult:
        """Open the exact separate profile used by previews and publishing."""
        if not self._exec_lock.acquire(blocking=False):
            return FacebookActionResult(False, self._t('هناك مهمة Facebook قيد التنفيذ.', 'A Facebook task is running.'))
        try:
            self._interactive_browser=True
            browser=self.fb()
            if browser.supports('open_interactive'):
                state=browser.open_interactive();backend=browser.browser_backend
            else:backend=browser.open_manual_login();state='not_connected'
            self._remember_status(state, backend)
            if state not in {'connected','not_connected','manual_login','verification_required'}:
                return FacebookActionResult(False,self._t('متصفح النشر لم يبق مفتوحاً. اطلب فتحه مجدداً.','The publishing browser did not remain open. Request it again.'))
            self.activity('facebook_publishing_login', backend)
            return FacebookActionResult(True, self._t(
                f'فتحت متصفح النشر المُدار ({backend}) على الكمبيوتر. سجّل الدخول يدوياً فيه واترك نافذته مفتوحة، ثم اطلب معاينة النشر.',
                f'Opened the managed publishing browser ({backend}) on the computer. Complete sign-in if requested, leave that window open, then request the publishing preview.'))
        except Exception as exc:
            self._remember_failure(exc)
            return FacebookActionResult(False, self._t(f'تعذر فتح متصفح النشر: {exc}', f'Could not open the publishing browser: {exc}'))
        finally:
            self._release_browser_after_action()
            self._exec_lock.release()

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
        # A deferred extension probe must not overwrite the active managed
        # profile's real status with an unrelated browser-not-connected error.
        if self._interactive_browser and self._fb is not None:
            if not self._exec_lock.acquire(blocking=False):
                return FacebookActionResult(False,self._t('مهمة Facebook قيد التنفيذ؛ لم يتغير فحص الاتصال.','A Facebook task is running; connection status was not changed.'))
            try:
                browser=self._fb
                if not browser.supports('connection_status'):
                    # Legacy backend compatibility: do not start a new browser
                    # in a background status check.
                    return FacebookActionResult(self._last_status=='connected',self.status_text())
                state=browser.connection_status()
                self._remember_status(state,browser.browser_backend)
                return FacebookActionResult(state=='connected',self.status_text())
            finally:self._exec_lock.release()
        result = self._verify_via_open_browser()
        if result is not None:
            return result
        # Never pop up a managed automation browser merely because the app opened.
        self._last_status = "browser_not_connected"
        self._last_backend = ""
        self.activity("facebook_connection_deferred", "normal browser extension not connected; manual check available")
        return FacebookActionResult(False, "Facebook: browser bridge not connected")

    @_browser_action
    def verify_session(self) -> FacebookActionResult:
        ext = self._verify_via_open_browser() if (getattr(self.settings, "facebook_browser_mode", "extension_first") == "extension_first" and not (self._interactive_browser and self._fb is not None)) else None
        if ext is not None:
            return ext
        try:
            self._interactive_browser=True
            browser=self.fb()
            status=browser.interactive_status() if browser.supports('interactive_status') else browser.verify_saved_session()
            self._remember_status(status, getattr(browser, "browser_backend", ""))
            self.activity("facebook_connection", f"{status}; {self._last_backend}")
            return FacebookActionResult(status == "connected", f"Facebook: {status}" + (f" — {self._last_backend}" if self._last_backend else ""))
        except Exception as exc:
            self._remember_failure(exc)
            self.activity("facebook_connection_error", f"{type(exc).__name__}: {exc}")
            return FacebookActionResult(False, self._t(f"فشل فحص جلسة Facebook: {exc}", f"Facebook session check failed: {exc}"))
        finally:
            self._release_browser_after_action()

    @_browser_action
    def discover_groups(self, limit: int = 500, deep: bool = True) -> FacebookActionResult:
        limit=max(1,min(int(limit),1000))
        if self.settings.facebook_browser_mode=='extension_first' and self.browser_bridge and self.browser_bridge.connected and not (self._interactive_browser and self._fb is not None):
            try:
                response=self.browser_bridge.execute('discover_facebook_groups',limit=limit,deep=deep,timeout=50 if deep else 15)
                if response.get('ok'):
                    groups=[]
                    for item in response.get('groups',[]):
                        if not isinstance(item,dict) or not item.get('name') or not item.get('url'):continue
                        try:self._facebook_url(item['url'],group=True)
                        except ValueError:continue
                        groups.append(item)
                    count=self.db.upsert_groups(groups)
                    self._last_status='connected';self._last_backend='normal-browser-extension'
                    return FacebookActionResult(True,self._t(f'قرأت {len(groups)} مجموعة من متصفحك وحفظت {count}.',f'Read {len(groups)} groups from your browser and saved {count}.'),count=count)
                if 'login' in str(response.get('error','')):
                    opened=self._open_manual_login_impl()
                    return FacebookActionResult(False,opened.message+' '+self._t('بعد الدخول اطلب تحديث الجروبات.','After signing in, request a group refresh.'))
            except Exception as exc:self.activity('browser_extension_fallback',type(exc).__name__)
        try:
            self._interactive_browser=True
            fb=self.fb();fb.ensure_logged_in()
            groups=fb.discover_joined_groups(limit=limit);count=self.db.upsert_groups(groups)
            self._last_status='connected';self._last_backend=fb.browser_backend
            return FacebookActionResult(True,self._t(f'تم التعرف على {count} مجموعة وحفظها.',f'Discovered and saved {count} groups.'),count=count)
        except Exception as exc:
            self._remember_failure(exc)
            self.activity('facebook_group_discovery_error',type(exc).__name__)
            from ..facebook_backend.facebook import LoginRequired,CheckpointDetected
            if isinstance(exc,(LoginRequired,CheckpointDetected)):
                return FacebookActionResult(False,self._t('فتحت متصفح Facebook. الحساب يحتاج تسجيل دخول أو تحقق؛ أكمله في النافذة المفتوحة، ثم اطلب تحديث الجروبات.','Facebook is open in the controlled browser. Complete its required sign-in or verification, then request a group refresh.'))
            return FacebookActionResult(False,self._t('تعذر اكتشاف المجموعات: '+str(exc),'Could not discover groups: '+str(exc)))

    @_browser_action
    def search_pages(self,query):
        import json
        query=' '.join(str(query or '').split())
        if not 1<=len(query)<=180:return FacebookActionResult(False,self._t('حدد اسم الصفحة التي تريد البحث عنها.','Give the page name to search for.'))
        try:
            self._interactive_browser=True
            browser=self.fb();pages=browser.search_pages(query,limit=10)
            self._remember_status('connected',browser.browser_backend)
            return FacebookActionResult(True,json.dumps({'query':query,'pages':pages},ensure_ascii=False),len(pages))
        except Exception as exc:
            self._remember_failure(exc)
            self.activity('facebook_page_search_error',type(exc).__name__)
            return FacebookActionResult(False,self._t('تعذر تأكيد نتيجة البحث في Facebook. إذا ظهرت نافذة دخول أكملها هناك. ','Could not confirm Facebook search results. Complete sign-in in the opened browser if prompted. ')+str(exc))

    @_browser_action
    def recent_posts(self,source_page_url,count=1):
        import json
        try:
            source=self._facebook_url(source_page_url);count=max(1,min(int(count),4))
            self._interactive_browser=True
            browser=self.fb();browser.ensure_logged_in()
            urls=browser.find_recent_post_urls(source,limit=count)
            self._remember_status('connected',browser.browser_backend)
            return FacebookActionResult(True,json.dumps({'source':source,'visible_recent_post_urls':urls,
                'published':False,'note':'Observed page order, excluding recognized pinned posts. No post text or publication is confirmed.'},ensure_ascii=False),len(urls))
        except Exception as exc:
            self._remember_failure(exc)
            return FacebookActionResult(False,self._t('تعذر قراءة روابط المنشورات: ','Could not read post links: ')+str(exc))

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
        if not self._exec_lock.acquire(blocking=False):
            return FacebookActionResult(False, self._t("هناك مهمة Facebook قيد التنفيذ؛ انتظر انتهاءها.", "Another Facebook task is running; wait for completion."))
        try:
            threading.Thread(target=self._execute_rule_guarded, args=(rule, True),
                             daemon=True, name=f"yaa-facebook-now-{rule_id}").start()
        except Exception:
            self._exec_lock.release()
            raise
        return FacebookActionResult(True, self._t(f"بدأ تنفيذ المهمة {rule_id} في الخلفية.", f"Task {rule_id} started in the background."))

    def _execute_rule_guarded(self, rule: dict, lock_acquired: bool = False) -> None:
        if not lock_acquired and not self._exec_lock.acquire(blocking=False):
            self.activity("facebook_rule_delayed", f"id={rule.get('id')}; another Facebook task is active")
            return
        rule_id = int(rule.get("id") or 0)
        self._task_cancel_event.clear()
        self._task_pause_event.clear()
        self._active_rule_id = rule_id or None
        self._current_step = "starting"
        self._progress_done = self._progress_total = 0
        self._started_at = time.time()
        result = {'status': 'failed', 'published': 0, 'submitted': 0, 'pending_approval': 0,
                  'failed': 0, 'skipped': 0, 'total': 0, 'error': ''}
        try:
            result = self._execute_rule(rule)
        except Exception as exc:
            result['error'] = f'{type(exc).__name__}: {exc}'
            self.activity('facebook_rule_error', f'id={rule_id}; {result["error"]}')
        finally:
            self._active_rule_id = None
            self._current_step = "idle"
            self._progress_done = self._progress_total = 0
            self._started_at = None
            self._task_cancel_event.clear()
            self._task_pause_event.clear()
            self.close_browser()
            self._exec_lock.release()
            self._complete(rule_id, result)

    def _execute_rule(self, rule: dict) -> dict:
        rule_id = int(rule['id'])
        result = {'status': 'completed', 'published': 0, 'submitted': 0, 'pending_approval': 0,
                  'failed': 0, 'skipped': 0, 'total': 0, 'error': ''}
        snapshot = bool(rule.get('approval_snapshot'))
        if snapshot:
            groups = list(rule.get('selected_groups') or [])
            posts = list(rule.get('post_urls') or [])
            if not groups or not posts or len(posts) > 4 or len(groups) > 500:
                raise ValueError('Approved Facebook target snapshot is missing or invalid; prepare a new preview')
        else:
            groups = self.db.list_groups(keyword=rule.get('group_keyword') or '', limit=int(rule.get('max_groups') or 100))
            posts = []
        if not groups:
            result.update(status='failed', error='No matching groups')
            self.activity('facebook_rule_no_groups', f'id={rule_id}')
            return result
        groups = [{'id': int(g['id']), 'name': str(g['name']),
                   'url': self._facebook_url(g['url'], group=True)} for g in groups]
        self._current_step = 'opening_facebook'
        fb = self.fb()
        fb.ensure_logged_in()
        if not snapshot:
            offset = 0 if rule.get('post_mode') == 'rotation' else max(0, int(rule.get('post_offset') or 0))
            count = max(1, min(4, int(rule.get('post_count') or 1)))
            candidates = fb.find_recent_post_urls(self._facebook_url(rule.get('source_page_url') or ''), limit=min(50, max(8, offset + count)))
            posts = list(dict.fromkeys(candidates))[offset:offset + count]
            if len(posts) != count:
                result.update(status='failed', error='The requested source posts were not found')
                return result
        posts = [self._facebook_url(u) for u in posts]
        result['total'] = len(posts) * len(groups)
        self._progress_total = result['total']
        self._current_step = 'sharing'
        interval = max(30, int(rule.get('interval_seconds') or 60))
        no_repeat = max(0, int(rule.get('no_repeat_days', 14)))
        pairs = [(post, group) for post in posts for group in groups]
        attempted = 0
        for index, (post_url, group) in enumerate(pairs):
            if not self._wait_if_paused():
                result['status'] = 'cancelled'
                break
            gid = group['id']
            if self.db.was_shared_recently(gid, post_url, no_repeat):
                result['skipped'] += 1
                self._progress_done = index + 1
                continue
            # Settings caps apply across all tasks and all posts, not once per group.
            now = datetime.now(timezone.utc).replace(tzinfo=None)
            hourly = max(1, int(getattr(self.settings, 'facebook_hourly_limit', 30)))
            daily = max(1, int(getattr(self.settings, 'facebook_daily_limit', 120)))
            if (self.db.submitted_share_count(now - timedelta(hours=1)) >= hourly or
                    self.db.submitted_share_count(now.replace(hour=0, minute=0, second=0, microsecond=0)) >= daily):
                result.update(status='limited', error='Facebook hourly or daily submission limit reached')
                break
            if attempted and self._task_cancel_event.wait(interval):
                result['status'] = 'cancelled'
                break
            if self._stop_event.is_set() or not self._wait_if_paused():
                result['status'] = 'cancelled'
                break
            attempted += 1
            try:
                self.activity('facebook_group_share_start', f'{index + 1}/{len(pairs)}; {group["name"]}; {post_url}')
                outcome = fb.share_post_to_group(group_name=group['name'], group_url=group['url'], post_url=post_url)
                if outcome not in {'published', 'submitted', 'pending_approval'}:
                    raise RuntimeError('Facebook did not confirm a submission outcome')
                self.db.record_share(rule_id, gid, post_url, outcome)
                result[outcome] += 1
                self.activity('facebook_share', f'{group["name"]}: {outcome}')
            except Exception as exc:
                result['failed'] += 1
                self.db.record_share(rule_id, gid, post_url, 'failed', str(exc))
                self.activity('facebook_share_error', f'{group["name"]}: {type(exc).__name__}: {exc}')
            self._progress_done = index + 1
        if result['status'] == 'completed' and result['failed']:
            result['status'] = 'partial' if any(result[k] for k in ('published', 'submitted', 'pending_approval')) else 'failed'
        self.activity('facebook_rule_done', f'id={rule_id}; {result}')
        return result
