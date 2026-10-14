from __future__ import annotations

import os
import re
import time
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


class FacebookAutomation:
    """
    Visible-browser automation only. No stealth, CAPTCHA bypass, proxy rotation,
    or anti-detection features are used.
    """

    def __init__(self, config: FacebookConfig | None = None):
        self.config = config or FacebookConfig()
        self.pw = None
        self.context = None
        self.page = None

    def start(self):
        if self.context:
            return
        _configure_bundled_playwright_browser()
        self.pw = sync_playwright().start()
        self.context = self.pw.chromium.launch_persistent_context(
            user_data_dir=str(self.config.profile_dir),
            headless=self.config.headless,
            viewport={"width": 1360, "height": 900},
            locale="ar-JO",
            args=["--disable-notifications"],
        )
        self.page = self.context.pages[0] if self.context.pages else self.context.new_page()

    def stop(self):
        try:
            if self.context:
                self.context.close()
        finally:
            self.context = None
            self.page = None
            if self.pw:
                self.pw.stop()
                self.pw = None

    def open_login(self):
        self.start()
        self.page.goto("https://www.facebook.com/", wait_until="domcontentloaded", timeout=60000)
        self.page.bring_to_front()

    def _check_checkpoint(self):
        url = (self.page.url or "").lower()
        body = ""
        try:
            body = self.page.locator("body").inner_text(timeout=1500).lower()
        except Exception:
            pass
        checkpoint_words = [
            "checkpoint", "security check", "confirm your identity", "two-factor authentication",
            "التحقق من الأمان", "تأكيد هويتك", "المصادقة الثنائية", "تحقق من هويتك",
        ]
        if any(x in url or x in body for x in checkpoint_words):
            raise CheckpointDetected("Facebook requested a security/checkpoint step; manual action is required.")

    def ensure_logged_in(self):
        self.start()
        self.page.goto("https://www.facebook.com/", wait_until="domcontentloaded", timeout=60000)
        self._check_checkpoint()
        try:
            if self.page.locator("input[name='email']").count() or self.page.locator("input[name='pass']").count():
                raise LoginRequired("Facebook login is required in the dedicated browser.")
        except PlaywrightTimeoutError:
            pass

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

        # Scan anchors repeatedly while gently scrolling. This avoids depending on a single CSS class.
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

        # Open group composer. Facebook labels change frequently, so try multiple semantic patterns.
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
            # Fallback: click a visible role=button containing common composer text.
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

        # Composer is usually an editable textbox/dialog textbox.
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
