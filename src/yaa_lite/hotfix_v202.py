"""Your Assistant Agent v2.0.2 runtime hotfixes.

This module is intentionally small and loaded from launcher.py before the UI is
created. It fixes three production issues without changing user data or the DB:

1. Hammer 2.1 legitimately emits [] when no tool call is needed. v2.0.1 treated
   that as a fatal protocol error and restarted llama-server repeatedly.
2. Hammer was lazy-loaded, so the first request paid the full model startup cost.
3. Facebook group discovery could verify the normal browser extension but then
   discover groups with a different Playwright profile.

The hotfix is idempotent and can be removed once the same changes are folded
into the core modules in a later release.
"""
from __future__ import annotations

import json
import threading
import time
import uuid
from typing import Any

_APPLIED = False


def _compact_messages(messages: list[dict], *, total_chars: int, per_message: int) -> list[dict]:
    """Keep routing prompts comfortably inside the 2K runtime context."""
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

    # Keep preference/system context plus the most recent conversational turns.
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
    """Return (name, args, is_empty_list), or None for non-JSON text."""
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


def _install_hammer_runtime_fix() -> None:
    from .ai.profiles import AgentProfile
    from .ai.runtime import LocalAIRuntime, _strip_reasoning

    if getattr(LocalAIRuntime, "_yaa_v202_patched", False):
        return

    def plain_reply(self, profile, messages, max_tokens, timeout, status, safe_mode) -> str:
        # Same Hammer model, but without a tool schema. This is the correct
        # fallback when Hammer says [] = no function call needed.
        plain_profile = AgentProfile(
            key=profile.key,
            title=profile.title,
            subtitle=profile.subtitle,
            model_filename=profile.model_filename,
            system_prompt=(
                "You are the conversational reply layer inside Your Assistant Agent. "
                "No application tool is needed for this turn. Reply naturally and directly "
                "in the user's language. Do not output JSON, tool calls, XML, or analysis. "
                "Keep the reply concise unless the user asks for detail."
            ),
        )
        compact = _compact_messages(messages, total_chars=5200, per_message=1300)
        msg = self._post_completion(
            plain_profile, compact, max_tokens, timeout, status, safe_mode, tools=None
        )
        if isinstance(msg, dict):
            text = _strip_reasoning(str(msg.get("content") or "")).strip()
            if text:
                return text
        raise RuntimeError("Hammer plain-chat fallback returned an empty reply")

    def tool_call(self, profile, messages, tools, max_tokens, timeout, status=None):
        # Tool selection needs far less history than natural conversation; this
        # avoids overflowing the 2048-token local context with nine JSON schemas.
        compact = _compact_messages(messages, total_chars=2400, per_message=900)

        def run(safe_mode: int):
            raw = self._hammer_completion(
                profile, compact, tools, max_tokens, timeout, status, safe_mode
            )
            decoded = _decode_hammer_call(raw)
            if decoded is not None:
                name, args, empty = decoded
                if empty:
                    # Official Hammer 2.1 template: [] means "no function call".
                    # Do not restart llama-server. Ask the same already-loaded
                    # model for the natural-language answer instead.
                    message = plain_reply(
                        self, profile, compact, max_tokens, timeout, status, safe_mode
                    )
                    return {"name": "respond", "arguments": {"message": message}, "content": raw}
                if name:
                    return {"name": name, "arguments": args, "content": raw}

            cleaned = _strip_reasoning(raw).strip()
            # Some GGUF conversions occasionally answer in prose despite the
            # strict tool prompt. Preserve a useful reply instead of rebooting.
            if cleaned and not cleaned.startswith(("[", "{")):
                return {"name": "respond", "arguments": {"message": cleaned}, "content": raw}

            # Malformed protocol output is not a server crash. Fall back to a
            # normal Hammer reply in-process; transport/runtime failures still
            # propagate and are handled by the existing restart ladder.
            message = plain_reply(
                self, profile, compact, max_tokens, timeout, status, safe_mode
            )
            return {"name": "respond", "arguments": {"message": message}, "content": raw}

        return self._run_with_retry(run, status=status)

    def chat(self, profile, messages, max_tokens, timeout, status=None):
        compact = _compact_messages(messages, total_chars=5200, per_message=1300)

        def run(safe_mode: int):
            # Chat is intentionally direct here. Routing has already happened in
            # SmartAgentController; a second tool-selection prompt only adds a
            # failure point and duplicated latency.
            return plain_reply(
                self, profile, compact, max_tokens, timeout, status, safe_mode
            )

        return self._run_with_retry(run, status=status)

    old_unload = LocalAIRuntime.unload_if_idle

    def unload_if_idle(self, idle_minutes: int) -> bool:
        if getattr(self, "_yaa_keep_warm", False):
            return False
        return old_unload(self, idle_minutes)

    LocalAIRuntime.tool_call = tool_call
    LocalAIRuntime.chat = chat
    LocalAIRuntime.unload_if_idle = unload_if_idle
    LocalAIRuntime._yaa_v202_patched = True


def _install_app_preload_fix() -> None:
    from .ai.profiles import HAMMER
    from .ui.app import App

    if getattr(App, "_yaa_v202_patched", False):
        return
    original = App._start_services_and_ui

    def _start_services_and_ui(self):
        original(self)
        runtime = getattr(self, "runtime", None)
        if runtime is None or getattr(self, "_hammer_preload_thread_started", False):
            return
        self._hammer_preload_thread_started = True
        runtime._yaa_keep_warm = True

        def warm():
            try:
                runtime.ensure_started(HAMMER)
                try:
                    self._activity("hammer_preload_ready", "Hammer 2.1 preloaded and kept warm")
                except Exception:
                    pass
            except Exception as exc:
                try:
                    self._activity("ai_error", f"preload: {type(exc).__name__}: {exc}")
                except Exception:
                    pass

        threading.Thread(target=warm, daemon=True, name="yaa-hammer-preload").start()

    App._start_services_and_ui = _start_services_and_ui
    App._yaa_v202_patched = True


def _install_browser_bridge_group_action() -> None:
    from .browser_bridge.server import BrowserBridge

    if getattr(BrowserBridge, "_yaa_v202_patched", False):
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
    BrowserBridge._yaa_v202_patched = True


def _install_facebook_group_fix() -> None:
    from .agent.facebook_service import FacebookActionResult, FacebookService

    if getattr(FacebookService, "_yaa_v202_patched", False):
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
                if result.get("ok") and isinstance(groups, list):
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
                error = str(result.get("error") or "extension returned no groups") if isinstance(result, dict) else "invalid extension result"
                self.activity("browser_extension_fallback", f"groups: {error}")
            except Exception as exc:
                self.activity("browser_extension_fallback", f"groups: {type(exc).__name__}: {exc}")

        # Fallback remains the dedicated managed Chromium profile.
        return original(self, limit)

    FacebookService.discover_groups = discover_groups
    FacebookService._yaa_v202_patched = True


def apply_hotfixes() -> None:
    global _APPLIED
    if _APPLIED:
        return
    _install_hammer_runtime_fix()
    _install_browser_bridge_group_action()
    _install_facebook_group_fix()
    _install_app_preload_fix()
    _APPLIED = True
