from __future__ import annotations

import os
import re
import subprocess
from dataclasses import dataclass
from pathlib import Path
from urllib.parse import urlsplit, urlunsplit

from playwright.sync_api import TimeoutError as PlaywrightTimeoutError
from playwright.sync_api import sync_playwright

from .paths import browser_profile_dir
from .branding import asset_path
from .browser_discovery import discover_installed_browsers
from .share_outcome import classify_share_result_text


def _configure_bundled_playwright_browser() -> None:
    """Use the Chromium copy bundled into the packaged Windows app when present."""
    bundled = asset_path("playwright-browsers")
    if bundled.exists():
        os.environ["PLAYWRIGHT_BROWSERS_PATH"] = str(bundled)


class FacebookError(RuntimeError):
    pass


class LoginRequired(FacebookError):
    pass


class ManualLoginInProgress(LoginRequired):
    """Raised when the manual login browser still owns the persistent profile."""


class CheckpointDetected(FacebookError):
    pass


@dataclass
class FacebookConfig:
    profile_dir: Path = browser_profile_dir()
    headless: bool = False
    locale: str = "en-US"
    browser_choice: str = "auto"
    browser_label: str = ""


class FacebookAutomation:
    """
    Facebook integration with two deliberately separate modes:

    1) Manual login: opens the user's installed Chromium browser directly, with
       the agent's dedicated persistent profile, without Playwright. Password,
       2FA and any Facebook challenge stay fully manual.
    2) Automation: after the saved session is verified, Playwright reuses the
       same dedicated profile for scheduled work. Chromium sandbox is enabled.

    No stealth, CAPTCHA solving/bypass, proxy rotation, or anti-detection
    features are used.
    """

    FACEBOOK_HOME = "https://www.facebook.com/"

    def __init__(self, config: FacebookConfig | None = None):
        self.config = config or FacebookConfig()
        self.pw = None
        self.context = None
        self.page = None
        self.browser_backend = ""
        self.manual_login_active = False
        self.manual_login_backend = ""

    def _context_alive(self) -> bool:
        if self.context is None:
            return False
        try:
            _ = self.context.pages
            return True
        except Exception:
            self.context = None
            self.page = None
            return False

    def is_open(self) -> bool:
        return self._context_alive()

    def _reset_playwright(self) -> None:
        self.context = None
        self.page = None
        if self.pw is not None:
            try:
                self.pw.stop()
            except Exception:
                pass
            self.pw = None

    @staticmethod
    def _profile_lock_error(exc: Exception) -> bool:
        text = str(exc).casefold()
        hints = (
            "user data directory is already in use",
            "processsingleton",
            "profile appears to be in use",
            "profile is in use",
            "cannot create process singleton",
        )
        return any(hint in text for hint in hints)

    def _launch(self, executable_path: Path | None, backend_name: str):
        kwargs = dict(
            user_data_dir=str(self.config.profile_dir),
            headless=self.config.headless,
            viewport={"width": 1360, "height": 900},
            locale=self.config.locale,
            chromium_sandbox=True,
            args=[
                "--disable-notifications",
                "--no-first-run",
                "--no-default-browser-check",
            ],
        )
        if executable_path is not None:
            kwargs["executable_path"] = str(executable_path)

        try:
            self.context = self.pw.chromium.launch_persistent_context(**kwargs)
        except Exception as exc:
            if self._profile_lock_error(exc):
                raise ManualLoginInProgress(
                    "Close the manual Facebook login browser first, then check the connection again."
                ) from exc
            raise
        self.page = self.context.pages[0] if self.context.pages else self.context.new_page()
        self.browser_backend = backend_name

    def _launch_selected_browser(self) -> bool:
        choice = (self.config.browser_choice or "auto").strip()
        if choice in {"", "auto"}:
            return False
        if choice == "bundled":
            _configure_bundled_playwright_browser()
            self._launch(None, self.config.browser_label or "Bundled Chromium")
            return True

        executable = Path(choice)
        if not executable.exists():
            raise FacebookError(f"Selected browser is no longer installed: {executable}")
        label = self.config.browser_label or executable.stem
        self._launch(executable, label)
        return True

    def _resolve_manual_browser(self) -> tuple[Path, str]:
        """Resolve a real installed browser for password/2FA entry.

        The bundled Playwright Chromium is intentionally not used for manual
        authentication when a normal installed Chromium browser is available.
        """
        choice = (self.config.browser_choice or "auto").strip()
        if choice not in {"", "auto", "bundled"}:
            executable = Path(choice)
            if not executable.exists():
                raise FacebookError(f"Selected browser is no longer installed: {executable}")
            return executable, self.config.browser_label or executable.stem

        candidates = [b for b in discover_installed_browsers() if b.support == "full"]
        if not candidates:
            candidates = [b for b in discover_installed_browsers() if b.support == "experimental"]
        if not candidates:
            raise FacebookError(
                "Manual Facebook login needs an installed Chromium browser such as Google Chrome or Microsoft Edge."
            )
        browser = candidates[0]
        return browser.executable, browser.name

    def manual_login_command(self, executable: Path, url: str | None = None) -> list[str]:
        """Build the direct browser command used for manual authentication.

        Kept separate for testing: importantly, it never contains --no-sandbox
        or Playwright/automation flags.
        """
        return [
            str(executable),
            f"--user-data-dir={self.config.profile_dir}",
            "--profile-directory=Default",
            "--new-window",
            url or self.FACEBOOK_HOME,
        ]

    def open_manual_login(self) -> str:
        """Open Facebook in a normal installed browser, without Playwright."""
        # Release any Playwright handle to this profile before normal Chrome/Edge
        # opens it. We intentionally do not kill the user's normal browser.
        self.stop()
        self.config.profile_dir.mkdir(parents=True, exist_ok=True)
        executable, label = self._resolve_manual_browser()
        command = self.manual_login_command(executable)
        try:
            creationflags = getattr(subprocess, "CREATE_NEW_PROCESS_GROUP", 0) if os.name == "nt" else 0
            subprocess.Popen(
                command,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
                close_fds=True,
                creationflags=creationflags,
            )
        except Exception as exc:
            raise FacebookError(f"Could not open {label} for manual Facebook login: {exc}") from exc
        self.manual_login_active = True
        self.manual_login_backend = label
        self.browser_backend = label
        return label

    # Backwards-compatible command name used by older engine/UI code.
    def open_login(self):
        return self.open_manual_login()

    def start(self):
        if self.manual_login_active:
            raise ManualLoginInProgress(
                "Manual Facebook login is still marked active. Close that browser and check the connection first."
            )

        if self._context_alive():
            try:
                pages = self.context.pages
                self.page = pages[0] if pages else self.context.new_page()
            except Exception:
                self.context = None
                self.page = None
            else:
                return

        self._reset_playwright()
        self.config.profile_dir.mkdir(parents=True, exist_ok=True)
        self.pw = sync_playwright().start()

        launch_errors: list[str] = []

        if (self.config.browser_choice or "auto") not in {"", "auto"}:
            try:
                if self._launch_selected_browser():
                    return
            except ManualLoginInProgress:
                self._reset_playwright()
                raise
            except Exception as exc:
                self._reset_playwright()
                raise FacebookError(f"Could not start {self.config.browser_label or 'the selected browser'}: {exc}") from exc

        candidates = [b for b in discover_installed_browsers() if b.support != "unsupported"]
        for browser in candidates:
            try:
                self._launch(browser.executable, browser.name)
                return
            except ManualLoginInProgress:
                self._reset_playwright()
                raise
            except Exception as exc:
                launch_errors.append(f"{browser.name}: {exc}")
                self.context = None
                self.page = None

        try:
            _configure_bundled_playwright_browser()
            self._launch(None, "Bundled Chromium")
            return
        except ManualLoginInProgress:
            self._reset_playwright()
            raise
        except Exception as exc:
            launch_errors.append(f"Bundled Chromium: {exc}")
            self._reset_playwright()
            raise FacebookError("Could not start the dedicated Facebook browser. " + " | ".join(launch_errors[-3:]))

    def stop(self):
        """Stop only the Playwright automation context; never kill manual browser."""
        try:
            if self._context_alive():
                self.context.close()
        except Exception:
            pass
        finally:
            self._reset_playwright()

    def connection_status(self) -> str:
        """Return status for an active automation context without navigation."""
        if self.manual_login_active:
            return "manual_login"
        if not self._context_alive():
            return "browser_closed"

        try:
            pages = self.context.pages
            urls = [(p.url or "").lower() for p in pages]
            verification_fragments = (
                "checkpoint",
                "two_step_verification",
                "two-factor",
                "confirm_identity",
                "security_check",
            )
            if any(any(fragment in url for fragment in verification_fragments) for url in urls):
                return "verification_required"

            cookies = self.context.cookies(["https://www.facebook.com", "https://facebook.com"])
            if any(c.get("name") == "c_user" and c.get("value") for c in cookies):
                return "connected"
            return "not_connected"
        except Exception:
            self.context = None
            self.page = None
            return "browser_closed"

    def verify_saved_session(self) -> str:
        """Verify the session saved by the manual browser, then close automation.

        The user should first close the manual Chrome/Edge window. If it still
        owns the profile, Playwright reports a profile lock and we return a clear
        ManualLoginInProgress error rather than hanging.
        """
        self.manual_login_active = False
        try:
            self.start()
            self.page.goto(self.FACEBOOK_HOME, wait_until="domcontentloaded", timeout=45000)
            self._check_checkpoint()
            cookies = self.context.cookies(["https://www.facebook.com", "https://facebook.com"])
            return "connected" if any(c.get("name") == "c_user" and c.get("value") for c in cookies) else "not_connected"
        finally:
            self.stop()

    def _check_checkpoint(self):
        url = (self.page.url or "").lower()
        body = ""
        try:
            body = self.page.locator("body").inner_text(timeout=1500).lower()
        except Exception:
            pass
        checkpoint_words = [
            "checkpoint", "security check", "confirm your identity", "two-factor authentication",
            "two_step_verification", "التحقق من الأمان", "تأكيد هويتك", "المصادقة الثنائية", "تحقق من هويتك",
        ]
        if any(x in url or x in body for x in checkpoint_words):
            raise CheckpointDetected("Facebook requested a security/checkpoint step; manual action is required.")

    def ensure_logged_in(self):
        self.start()
        self.page.goto(self.FACEBOOK_HOME, wait_until="domcontentloaded", timeout=60000)
        self._check_checkpoint()
        if self.connection_status() != "connected":
            try:
                if self.page.locator("input[name='email']").count() or self.page.locator("input[name='pass']").count():
                    raise LoginRequired("Facebook login is required. Use manual login from the Dashboard first.")
            except PlaywrightTimeoutError:
                pass
            raise LoginRequired("Facebook login is required. Use manual login from the Dashboard first.")

    @staticmethod
    def _clean_facebook_url(url: str) -> str:
        p = urlsplit(url)
        return urlunsplit((p.scheme, p.netloc, p.path.rstrip("/"), "", ""))

    def find_recent_post_urls(self, page_url: str, limit: int = 8) -> list[str]:
        self.start()
        self.page.goto(page_url, wait_until="domcontentloaded", timeout=60000)
        self._check_checkpoint()
        self.page.wait_for_timeout(3500)
        urls: list[str] = []
        seen = set()

        for _ in range(4):
            hrefs = self.page.locator("a[href]").evaluate_all("els => els.map(e => e.href)")
            for href in hrefs:
                if not isinstance(href, str) or "facebook.com" not in href:
                    continue
                if not re.search(r"/(posts|videos|reel|photo(?:s)?)/", href):
                    continue
                clean = self._clean_facebook_url(href)
                if clean not in seen:
                    seen.add(clean)
                    urls.append(clean)
                    if len(urls) >= limit:
                        return urls
            self.page.mouse.wheel(0, 1200)
            self.page.wait_for_timeout(1200)
        return urls

    def post_link_to_group(self, group_url: str, post_url: str, message_prefix: str = ""):
        self.start()
        self.page.goto(group_url, wait_until="domcontentloaded", timeout=60000)
        self._check_checkpoint()
        self.page.wait_for_timeout(2500)

        patterns = [
            r"Write something", r"Create (?:a )?post", r"What's on your mind",
            r"اكتب شيئ", r"إنشاء منشور", r"بم تفكر", r"ما الذي تفكر",
        ]
        opened = False
        for pat in patterns:
            rx = re.compile(pat, re.I)
            for role in ("button", "textbox"):
                try:
                    loc = self.page.get_by_role(role, name=rx).first
                    if loc.count() and loc.is_visible(timeout=800):
                        loc.click(timeout=3000)
                        opened = True
                        break
                except Exception:
                    pass
            if opened:
                break

        if not opened:
            for pat in patterns:
                try:
                    loc = self.page.locator("[role='button']").filter(has_text=re.compile(pat, re.I)).first
                    if loc.count() and loc.is_visible(timeout=800):
                        loc.click(timeout=3000)
                        opened = True
                        break
                except Exception:
                    pass

        if not opened:
            raise FacebookError("Could not locate the Facebook group post composer.")

        self.page.wait_for_timeout(1200)
        text = f"{message_prefix.strip()}\n{post_url}".strip()

        candidates = [
            self.page.locator("[role='dialog'] [role='textbox'][contenteditable='true']"),
            self.page.locator("[role='textbox'][contenteditable='true']"),
            self.page.locator("div[contenteditable='true']"),
        ]
        editor = None
        for c in candidates:
            try:
                if c.count():
                    for i in range(min(c.count(), 8)):
                        item = c.nth(i)
                        if item.is_visible(timeout=500):
                            editor = item
                            break
                if editor:
                    break
            except Exception:
                pass
        if not editor:
            raise FacebookError("Could not locate the Facebook post editor.")

        editor.click()
        editor.fill(text)
        self.page.wait_for_timeout(1800)
        self._check_checkpoint()

        post_rx = re.compile(r"^(Post|Publish|نشر)$", re.I)
        post_button = None
        try:
            dialog = self.page.locator("[role='dialog']")
            loc = dialog.get_by_role("button", name=post_rx).last
            if loc.count() and loc.is_visible(timeout=1500):
                post_button = loc
        except Exception:
            pass
        if post_button is None:
            try:
                loc = self.page.get_by_role("button", name=post_rx).last
                if loc.count() and loc.is_visible(timeout=1500):
                    post_button = loc
            except Exception:
                pass
        if post_button is None:
            raise FacebookError("Could not locate the final Post/نشر button.")

        post_button.click(timeout=5000)
        self.page.wait_for_timeout(2500)
        self._check_checkpoint()

    @staticmethod
    def _normalize_group_candidate(href: str, text: str = "", aria: str = "", title: str = "") -> dict | None:
        """Normalize one Facebook group link discovered in the normal Groups UI."""
        href = str(href or "").strip()
        if not href:
            return None
        if href.startswith("/"):
            href = "https://www.facebook.com" + href
        try:
            parsed = urlsplit(href)
        except Exception:
            return None
        host = (parsed.netloc or "").casefold()
        if host not in {"facebook.com", "www.facebook.com", "m.facebook.com"}:
            return None
        parts = [part for part in parsed.path.split("/") if part]
        if len(parts) < 2 or parts[0].casefold() != "groups":
            return None
        slug = parts[1].strip()
        reserved = {
            "feed", "discover", "create", "joins", "for_you", "notifications",
            "gaming", "category", "search", "membership", "requests",
        }
        if not slug or slug.casefold() in reserved:
            return None

        raw_name = str(text or aria or title or "").strip()
        # Facebook group cards often include metadata on later lines. The first
        # meaningful line is normally the group name and is much more stable.
        lines = [re.sub(r"\s+", " ", x).strip() for x in raw_name.splitlines() if x.strip()]
        name = lines[0] if lines else ""
        generic = {
            "groups", "your groups", "groups you've joined", "groups you’ve joined",
            "المجموعات", "مجموعاتك", "المجموعات التي انضممت إليها",
            "see all", "عرض الكل", "view all",
        }
        if not name or name.casefold() in generic:
            return None
        return {
            "name": name[:180],
            "url": f"https://www.facebook.com/groups/{slug}",
            "tags": "",
        }

    def discover_joined_groups(self, limit: int = 200) -> list[dict]:
        """Discover groups visible to the signed-in profile from Facebook's normal UI.

        The primary page is Groups you've joined (/groups/joins/). A Groups feed
        fallback is also scanned because Facebook rolls out different desktop
        layouts. No private data is fetched outside what the signed-in profile can
        already see and no checkpoint is bypassed.
        """
        self.ensure_logged_in()
        limit = max(1, int(limit))
        groups: list[dict] = []
        seen: set[str] = set()
        targets = (
            "https://www.facebook.com/groups/joins/",
            "https://www.facebook.com/groups/feed/",
        )

        for target in targets:
            self.page.goto(target, wait_until="domcontentloaded", timeout=60000)
            self._check_checkpoint()
            self.page.wait_for_timeout(2200)
            stagnant_rounds = 0

            for _ in range(18):
                try:
                    anchors = self.page.locator("a[href*='/groups/']").evaluate_all(
                        """els => els.map(a => ({
                            href: a.href || a.getAttribute('href') || '',
                            text: (a.innerText || a.textContent || '').trim(),
                            aria: a.getAttribute('aria-label') || '',
                            title: a.getAttribute('title') || ''
                        }))"""
                    )
                except Exception:
                    anchors = []

                before = len(groups)
                for item in anchors or []:
                    if not isinstance(item, dict):
                        continue
                    candidate = self._normalize_group_candidate(
                        item.get("href", ""),
                        item.get("text", ""),
                        item.get("aria", ""),
                        item.get("title", ""),
                    )
                    if not candidate or candidate["url"] in seen:
                        continue
                    seen.add(candidate["url"])
                    groups.append(candidate)
                    if len(groups) >= limit:
                        return groups

                if len(groups) == before:
                    stagnant_rounds += 1
                else:
                    stagnant_rounds = 0

                # Infinite-scroll layouts need a few scrolls even after one empty
                # round. Three consecutive empty rounds means this page is spent.
                if stagnant_rounds >= 3:
                    break
                try:
                    self.page.mouse.wheel(0, 1900)
                except Exception:
                    pass
                self.page.wait_for_timeout(900)
                self._check_checkpoint()

        return groups

    @staticmethod
    def classify_share_result_text(text: str) -> str:
        return classify_share_result_text(text)

    def _share_feedback_text(self) -> str:
        chunks = []
        for selector in ("[role='alert']", "[role='status']", "[role='dialog']"):
            try:
                loc = self.page.locator(selector)
                count = min(loc.count(), 12)
                for i in range(count):
                    item = loc.nth(i)
                    try:
                        if item.is_visible(timeout=250):
                            txt = item.inner_text(timeout=700).strip()
                            if txt:
                                chunks.append(txt)
                    except Exception:
                        pass
            except Exception:
                pass
        return "\n".join(chunks)[-12000:]

    def share_post_to_group(self, group_name: str, group_url: str, post_url: str) -> str:
        """Use Facebook's own Share -> Share to a group flow from the signed-in profile.

        This intentionally fails closed if Facebook does not offer native group
        sharing for the selected post; it does not silently substitute a different
        posting method.
        """
        self.ensure_logged_in()
        self.page.goto(post_url, wait_until="domcontentloaded", timeout=60000)
        self._check_checkpoint()
        self.page.wait_for_timeout(2200)

        share_rx = re.compile(r"^(Share|مشاركة)$", re.I)
        share_button = None
        candidates = [
            self.page.get_by_role("button", name=share_rx),
            self.page.locator("[role='button']").filter(has_text=share_rx),
        ]
        for loc in candidates:
            try:
                if loc.count():
                    for i in range(min(loc.count(), 12)):
                        item = loc.nth(i)
                        if item.is_visible(timeout=500):
                            share_button = item
                            break
                if share_button is not None:
                    break
            except Exception:
                pass
        if share_button is None:
            raise FacebookError("Could not locate the Share/مشاركة control on the source post.")
        share_button.click(timeout=5000)
        self.page.wait_for_timeout(900)
        self._check_checkpoint()

        to_group_rx = re.compile(r"(Share to (?:a )?group|مشاركة (?:في|إلى) مجموعة)", re.I)
        to_group = None
        for role in ("menuitem", "button"):
            try:
                loc = self.page.get_by_role(role, name=to_group_rx).first
                if loc.count() and loc.is_visible(timeout=1000):
                    to_group = loc
                    break
            except Exception:
                pass
        if to_group is None:
            try:
                loc = self.page.get_by_text(to_group_rx).first
                if loc.count() and loc.is_visible(timeout=1000):
                    to_group = loc
            except Exception:
                pass
        if to_group is None:
            raise FacebookError("Facebook did not offer 'Share to a group' for this post.")
        to_group.click(timeout=5000)
        self.page.wait_for_timeout(1000)
        self._check_checkpoint()

        search_rx = re.compile(r"(Search groups|Search for a group|البحث عن مجموعة|ابحث عن مجموعة|بحث في المجموعات)", re.I)
        search = None
        for role in ("textbox", "combobox"):
            try:
                loc = self.page.get_by_role(role, name=search_rx).first
                if loc.count() and loc.is_visible(timeout=1000):
                    search = loc
                    break
            except Exception:
                pass
        if search is None:
            try:
                loc = self.page.locator("input[placeholder]").filter(has=self.page.locator("xpath=.."))
            except Exception:
                loc = None
            # Generic visible input fallback inside the share dialog.
            try:
                inputs = self.page.locator("[role='dialog'] input")
                for i in range(min(inputs.count(), 6)):
                    item = inputs.nth(i)
                    if item.is_visible(timeout=500):
                        search = item
                        break
            except Exception:
                pass
        if search is not None:
            try:
                search.fill(group_name)
                self.page.wait_for_timeout(1200)
            except Exception:
                pass

        target = None
        exact_rx = re.compile(rf"^{re.escape(group_name.strip())}$", re.I)
        for role in ("button", "option", "menuitem", "link"):
            try:
                loc = self.page.get_by_role(role, name=exact_rx).first
                if loc.count() and loc.is_visible(timeout=900):
                    target = loc
                    break
            except Exception:
                pass
        if target is None:
            try:
                loc = self.page.get_by_text(group_name, exact=True).first
                if loc.count() and loc.is_visible(timeout=900):
                    target = loc
            except Exception:
                pass
        if target is None:
            raise FacebookError(f"Could not find the target group in the native share dialog: {group_name}")
        target.click(timeout=5000)
        self.page.wait_for_timeout(1100)
        self._check_checkpoint()

        final_rx = re.compile(r"^(Post|Share|Publish|نشر|مشاركة)$", re.I)
        final_button = None
        try:
            dialog = self.page.locator("[role='dialog']")
            loc = dialog.get_by_role("button", name=final_rx).last
            if loc.count() and loc.is_visible(timeout=1200):
                final_button = loc
        except Exception:
            pass
        if final_button is None:
            try:
                loc = self.page.get_by_role("button", name=final_rx).last
                if loc.count() and loc.is_visible(timeout=1200):
                    final_button = loc
            except Exception:
                pass
        if final_button is None:
            raise FacebookError("Could not locate the final Post/Share button in Facebook's share dialog.")
        final_button.click(timeout=5000)
        self.page.wait_for_timeout(2200)
        self._check_checkpoint()

        # Facebook groups may require admin/moderator approval. That is a valid
        # submission state, not a failed automation attempt. Capture the visible
        # post-submit feedback and return a semantic outcome to the engine.
        feedback = self._share_feedback_text()
        return self.classify_share_result_text(feedback)

    def test_group_access(self, group_url: str) -> bool:
        self.start()
        self.page.goto(group_url, wait_until="domcontentloaded", timeout=60000)
        self._check_checkpoint()
        return "facebook.com" in self.page.url
