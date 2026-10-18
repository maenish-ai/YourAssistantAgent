"""Groq streaming responses with normal OpenAI-compatible tool-call assembly.

Uses streaming only for UI requests with a status callback. Background/legacy
unit-test calls without a callback keep their established v2.3 code path.
"""
from __future__ import annotations

import json
import time

import requests

from .ai.runtime import GROQ_API_URL, GROQ_MODEL, LocalAIError, LocalAIRuntime, _compact_native_messages, _strip_reasoning, get_groq_api_key

_APPLIED = False
PREFIX = "__YAA_STREAM_V250__:"


def assemble_stream(lines, on_text=None):
    """Return content and tool calls from OpenAI-compatible SSE data lines."""
    content = ""
    calls = {}
    last_visible = 0
    for raw in lines:
        if not raw:
            continue
        line = raw.decode("utf-8", errors="replace") if isinstance(raw, bytes) else str(raw)
        if not line.startswith("data:"):
            continue
        raw_json = line[5:].strip()
        if raw_json == "[DONE]":
            break
        try:
            event = json.loads(raw_json)
        except (ValueError, TypeError):
            continue
        for choice in event.get("choices") or []:
            delta = choice.get("delta") or {}
            if delta.get("content"):
                content += str(delta["content"])
                if on_text and len(content) - last_visible >= 18:
                    on_text(content)
                    last_visible = len(content)
            for tool in delta.get("tool_calls") or []:
                idx = int(tool.get("index", 0))
                c = calls.setdefault(idx, {"id": "", "name": "", "arguments": ""})
                if tool.get("id"):
                    c["id"] += str(tool["id"])
                fn = tool.get("function") or {}
                if fn.get("name"):
                    c["name"] += str(fn["name"])
                if fn.get("arguments"):
                    c["arguments"] += str(fn["arguments"])
    if on_text and len(content) > last_visible:
        on_text(content)
    normalized = []
    for idx, tool in sorted(calls.items()):
        name = tool["name"].strip()
        if not name:
            continue
        try:
            parsed = json.loads(tool["arguments"] or "{}")
            if not isinstance(parsed, dict):
                parsed = {}
        except (TypeError, ValueError):
            parsed = {}
        args_json = json.dumps(parsed, ensure_ascii=False, separators=(",", ":"))
        normalized.append({
            "id": tool["id"] or f"call_stream_{idx}",
            "type": "function",
            "function": {"name": name, "arguments": args_json},
            "name": name, "arguments": parsed,
        })
    return {"content": _strip_reasoning(content).strip(), "tool_calls": normalized}


def apply_stream_v250():
    global _APPLIED
    if _APPLIED:
        return
    original = LocalAIRuntime.native_turn

    def native_turn(self, profile, messages, tools, max_tokens, timeout, status=None):
        if status is None:
            return original(self, profile, messages, tools, max_tokens, timeout, status=status)
        key = get_groq_api_key(required=True)
        compact = _compact_native_messages(messages)
        payload = {
            "model": GROQ_MODEL,
            "messages": [{"role": "system", "content": profile.system_prompt}] +
                        [self._api_message(m) for m in compact],
            "temperature": 0.15,
            "max_completion_tokens": max(1024, min(int(max_tokens), 2048)),
            "reasoning_effort": "low",
            "stream": True,
        }
        if tools:
            payload["tools"] = tools
            payload["tool_choice"] = "auto"
            payload["parallel_tool_calls"] = False
        status("GroqCloud is handling the request…")
        try:
            with requests.post(
                GROQ_API_URL,
                headers={"Authorization": f"Bearer {key}", "Content-Type": "application/json",
                         "User-Agent": "YourAssistantAgent/2.5"},
                json=payload, stream=True, timeout=(5, min(max(10, int(timeout)), 22)),
            ) as response:
                if response.status_code == 401:
                    raise LocalAIError("GroqCloud rejected API key; check GROQ_API_KEY.")
                if response.status_code == 429:
                    raise LocalAIError("وصلت حد Groq المجاني مؤقتًا. جرّب بعد قليل.")
                if not response.ok:
                    # Invalid model/tool parameters should surface promptly,
                    # without retrying and keeping the user waiting a minute.
                    raise LocalAIError(f"GroqCloud HTTP {response.status_code}: {response.text[:180]}")
                turn = assemble_stream(response.iter_lines(),
                                       on_text=lambda v: status(PREFIX + v[-2000:]))
        except requests.RequestException as exc:
            raise LocalAIError(f"GroqCloud connection timed out or failed: {type(exc).__name__}") from exc
        if not turn["content"] and not turn["tool_calls"]:
            raise LocalAIError("GroqCloud stream ended without a usable response.")
        self.last_used_monotonic = time.monotonic()
        return turn

    LocalAIRuntime.native_turn = native_turn
    _APPLIED = True
