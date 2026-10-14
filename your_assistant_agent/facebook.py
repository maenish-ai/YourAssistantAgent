from __future__ import annotations

import os
import re
import shutil
from dataclasses import dataclass
from pathlib import Path
from urllib.parse import urlsplit, urlunsplit

from playwright.sync_api import TimeoutError as PlaywrightTimeoutError
from playwright.sync_api import sync_playwright

from .paths import browser_profile_dir
from .branding import asset_path


def _configure_bundled_playwright_browser() -> None:
    """Use the Chromium copy bundled into the packaged Windows app when present."""
    bundled = asset_path("playwright-browsers")
    if bundled.exists():
        os.environ["PLAYWRIGHT_BROWSERS_PATH"] = str(bundled)


def _system_browser_candidates() -> list[tuple[str, Path]]:
    """Return installed Chrome/Edge executables in preferred order on Windows."""
    if os.name != "nt":
        return []

    paths: list[tuple[str, Path]] = []
    env = os.environ
    raw = [
        ("Google Chrome", Path(env.get("PROGRAMFILES", "")) / "Google/Chrome/Application/chrome.exe"),
        ("Google Chrome", Path(env.get("PROGRAMFILES(X86)", "")) / "Google/Chrome/Application/chrome.exe"),
        ("Google Chrome", Path(env.get("LOCALAPPDATA", "")) / "Google/Chrome/Application/chrome.exe"),
        ("Microsoft Edge", Path(env.get("PROGRAMFILES(X86)", "")) / "Microsoft/Edge/Application/msedge.exe"),
        ("Microsoft Edge", Path(env.get("PROGRAMFILES", "")) / "Microsoft/Edge/Application/msedge.exe"),
        ("Microsoft Edge", Path(env.get("LOCALAPPDATA", "")) / "Microsoft/Edge/Application/msedge.exe"),
    ]

    seen: set[str] = set()
    for name, path in raw:
        text = str(path)
        if text and path.exists() and text.lower() not in seen:
            seen.add(text.lower())
            paths.append((name, path))

    # Also honor browser executables available on PATH.
    for exe, name in (("chrome.exe", "Google Chrome"), ("msedge.exe", "Microsoft Edge")):
        found = shutil.which(exe)
        if found and found.lower() not in seen:
            seen.add(found.lower())
            paths.append((name, Path(found)))
    return paths


class FacebookError(RuntimeError):
    pass


class LoginRequired(FacebookError):
    pass


class CheckpointDetected(FacebookError):
    pass


@dataclass
class FacebookConfig:
    profile_dir: Path = browser_profile_dir()
    headless: bool = False
    locale: str = "en-US"


class FacebookAutomation:
    """
    Visible-browser automation only. Facebook credentials are entered only on
    facebook.com. A dedicated persistent browser profile stores the session on
    the user's own Windows account. No stealth, CAPTCHA bypass, proxy rotation,
    or anti-detection features are used.
    """

    def __init__(self, config: FacebookConfig | None = None):
        self.config = config or FacebookConfig()
        self.pw = None
        self.context = None
        self.page = None
        self.browser_backend = ""

    def _context_alive(self) -> bool:
        if self.context is None:
            return False
        try:
            # Accessing pages raises if the user has closed the browser/context.
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

    def _launch(self, executable_path: Path | None, backend_name: str):
        kwargs = dict(
            user_data_dir=str(self.config.profile_dir),
            headless=self.config.headless,
            viewport={"width": 1360, "height": 900},
            locale=self.config.locale,
            args=[
                "--disable-notifications",
                "--no-first-run",
                "--no-default-browser-check",
            ],
        )
        if executable_path is not None:
            kwargs["executable_path"] = str(executable_path)

        self.context = self.pw.chromium.launch_persistent_context(**kwargs)
        self.page = self.context.pages[0] if self.context.pages else self.context.new_page()
        self.browser_backend = backend_name

    def start(self):
        if self._context_alive():
            try:
                pages = self.context.pages
                self.page = pages[0] if pages else self.context.new_page()
            except Exception:
                self.context = None
                self.page = None
            else:
                return

        # A browser window closed by the user leaves a stale Playwright object.
        # Restart Playwright cleanly while keeping the same persistent profile.
        self._reset_playwright()
        self.config.profile_dir.mkdir(parents=True, exist_ok=True)
        self.pw = sync_playwright().start()

        launch_errors: list[str] = []
        for name, executable in _system_browser_candidates():
            try:
                self._launch(executable, name)
                return
            except Exception as exc:
                launch_errors.append(f"{name}: {exc}")
                self.context = None
                self.page = None

        # Fallback keeps the app usable when Chrome/Edge is unavailable.
        try:
            _configure_bundled_playwright_browser()
            self._launch(None, "Bundled Chromium")
            return
        except Exception as exc:
            launch_errors.append(f"Bundled Chromium: {exc}")
            self._reset_playwright()
            raise FacebookError("Could not start the dedicated Facebook browser. " + " | ".join(launch_errors[-3:]))

    def stop(self):
        try:
            if self._context_alive():
                self.context.close()
        except Exception:
            pass
        finally:
            self._reset_playwright()

    def open_login(self):
        self.start()
        self.page.goto("https://www.facebook.com/", wait_until="domcontentloaded", timeout=60000)
        self.page.bring_to_front()

    def connection_status(self) -> str:
        """Return a lightweight status without navigating away from the user's page."""
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
            # If the user closes the browser during this check, the profile still
            # remains on disk and will be reused next time.
            self.context = None
            self.page = None
            return "browser_closed"

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
        self.page.goto("https://www.facebook.com/", wait_until="domcontentloaded", timeout=60000)
        self._check_checkpoint()
        if self.connection_status() != "connected":
            try:
                if self.page.locator("input[name='email']").count() or self.page.locator("input[name='pass']").count():
                    raise LoginRequired("Facebook login is required in the dedicated browser.")
            except PlaywrightTimeoutError:
                pass
            raise LoginRequired("Facebook login is required in the dedicated browser.")

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

    def test_group_access(self, group_url: str) -> bool:
        self.start()
        self.page.goto(group_url, wait_until="domcontentloaded", timeout=60000)
        self._check_checkpoint()
        return "facebook.com" in self.page.url
