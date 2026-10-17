"""Compatibility fixes carried forward from v2.0.2.

v2.1 moved the primary AI runtime from Hammer to Qwen3, so the old Hammer
runtime/preload monkey-patches must no longer be installed.  The Facebook
normal-browser fixes are still useful and are kept here until they are folded
into the core Facebook service in a later cleanup release.
"""
from __future__ import annotations

import json
import threading
import time
import uuid
from typing import Any

_APPLIED = False


def _compact_messages(messages: list[dict], *, total_chars: int, per_message: int) -> list[dict]:
    """Legacy v2.0.2 helper retained for compatibility/tests."""
    systems: list[dict] = []
    normal: list[dict] = []
    for msg in messages or []:
        role = str(msg.get("role") or "user")
        content = str(msg.get("content") or "")
        item = {"role": role, "content": content[-per_message:]}
        if role == "system":
            systems.append(item)
        else:
            normal.append(item)

    out: list[dict] = []
    used = 0
    for msg in systems[-2:]:
        text = msg["content"][-min(per_message, 900):]
        if used + len(text) <= total_chars:
            out.append({"role": "system", "content": text})
            used += len(text)

    tail: list[dict] = []
    for msg in reversed(normal):
        text = msg["content"][-per_message:]
        if tail and used + len(text) > total_chars:
            break
        tail.append({"role": msg["role"], "content": text})
        used += len(text)
        if len(tail) >= 3:
            break
    out.extend(reversed(tail))
    return out


def _decode_hammer_call(text: str) -> tuple[str, dict[str, Any], bool] | None:
    """Legacy parser retained so upgrades/tests from v2.0.2 stay compatible."""
    from .ai.runtime import _strip_reasoning

    cleaned = _strip_reasoning(text or "").strip()
    if not cleaned:
        return None
    if cleaned.startswith("```json"):
        cleaned = cleaned[7:].strip()
    elif cleaned.startswith("```"):
        cleaned = cleaned[3:].strip()
    if cleaned.endswith("```"):
        cleaned = cleaned[:-3].strip()

    try:
        obj = json.loads(cleaned)
    except Exception:
        return None

    if isinstance(obj, list):
        if not obj:
            return "respond", {}, True
        obj = obj[0] if isinstance(obj[0], dict) else None
    if not isinstance(obj, dict):
        return None

    name = str(obj.get("name") or obj.get("tool") or "").strip()
    args = obj.get("arguments", obj.get("params", {}))
    if isinstance(args, str):
        try:
            args = json.loads(args)
        except Exception:
            args = {"value": args}
    return name, args if isinstance(args, dict) else {}, False


def _install_browser_bridge_group_action() -> None:
    from .browser_bridge.server import BrowserBridge

    if getattr(BrowserBridge, "_yaa_v202_browser_patched", False):
        return
    original = BrowserBridge.queue_command

    def queue_command(self, action: str, **arguments) -> str:
        if action != "discover_facebook_groups":
            return original(self, action, **arguments)
        cid = uuid.uuid4().hex
        cmd = {
            "id": cid,
            "action": action,
            "arguments": arguments,
            "created_at": time.time(),
        }
        with self._lock:
            self._commands.append(cmd)
            self._result_events[cid] = threading.Event()
        self.activity("browser_command_queued", f"{action}; id={cid[:8]}")
        return cid

    BrowserBridge.queue_command = queue_command
    BrowserBridge._yaa_v202_browser_patched = True


def _install_facebook_group_fix() -> None:
    from .agent.facebook_service import FacebookActionResult, FacebookService

    if getattr(FacebookService, "_yaa_v202_browser_patched", False):
        return
    original = FacebookService.discover_groups

    def discover_groups(self, limit: int = 500):
        limit = max(1, min(int(limit), 1000))
        bridge = getattr(self, "browser_bridge", None)
        mode = getattr(self.settings, "facebook_browser_mode", "extension_first")
        if mode == "extension_first" and bridge is not None and bridge.connected:
            try:
                result = bridge.execute(
                    "discover_facebook_groups", limit=limit, timeout=55
                )
                groups = result.get("groups") if isinstance(result, dict) else None
                if isinstance(result, dict) and result.get("ok") and isinstance(groups, list):
                    cleaned = []
                    for item in groups:
                        if not isinstance(item, dict):
                            continue
                        name = str(item.get("name") or "").strip()
                        url = str(item.get("url") or "").strip()
                        if name and "/groups/" in url:
                            cleaned.append({"name": name[:180], "url": url, "tags": ""})
                    count = self.db.upsert_groups(cleaned)
                    self._last_status = "connected"
                    self._last_backend = "normal-browser-extension"
                    self.activity("facebook_groups_discovered", f"saved={count}; backend=extension")
                    return FacebookActionResult(
                        True,
                        self._t(
                            f"تم التعرف على {count} مجموعة من حساب Facebook المفتوح وحفظها.",
                            f"Discovered and saved {count} groups from the open Facebook account.",
                        ),
                        count=count,
                    )
                error = (
                    str(result.get("error") or "extension returned no groups")
                    if isinstance(result, dict)
                    else "invalid extension result"
                )
                self.activity("browser_extension_fallback", f"groups: {error}")
            except Exception as exc:
                self.activity("browser_extension_fallback", f"groups: {type(exc).__name__}: {exc}")

        # Fallback remains the dedicated managed Chromium profile.
        return original(self, limit)

    FacebookService.discover_groups = discover_groups
    FacebookService._yaa_v202_browser_patched = True


def apply_hotfixes() -> None:
    """Apply only browser/Facebook compatibility fixes in v2.1+.

    The v2.0.2 Hammer runtime and preload monkey-patches are intentionally NOT
    installed because Qwen3 owns the AI runtime and pre-warms itself natively.
    """
    global _APPLIED
    if _APPLIED:
        return
    _install_browser_bridge_group_action()
    _install_facebook_group_fix()
    _APPLIED = True
