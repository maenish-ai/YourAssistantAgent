"""Groq streaming responses with normal OpenAI-compatible tool-call assembly.

Uses streaming only for UI requests with a status callback. Background/legacy
unit-test calls without a callback keep their established v2.3 code path.
"""
from __future__ import annotations

import json
import time

import requests

from .ai.runtime import (GROQ_API_URL, GROQ_MODEL, LocalAIError, LocalAIRuntime,
                         _compact_native_messages, _groq_http_error,
                         _normalize_tool_calls, _strip_reasoning, get_groq_api_key)

_APPLIED = False
PREFIX = "__YAA_STREAM_V250__:"


def assemble_stream(lines, on_text=None):
    """Return content and tool calls from OpenAI-compatible SSE data lines."""
    content = ""
    calls = {}
    last_visible = 0
    finish_reason = None
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
            raise LocalAIError("GroqCloud returned invalid stream data.", code="invalid_response") from None
        if not isinstance(event, dict):
            raise LocalAIError("GroqCloud returned invalid stream data.", code="invalid_response")
        if event.get("error"):
            error = event["error"]
            code = error.get("code") if isinstance(error, dict) else None
            category = "tool_call" if isinstance(code, str) and code in {"tool_use_failed", "tool_call_validation_failed"} else "invalid_response"
            raise LocalAIError("GroqCloud reported a stream error.", code=category)
        for choice in event.get("choices") or []:
            if not isinstance(choice, dict):
                raise LocalAIError("GroqCloud returned an invalid stream choice.", code="invalid_response")
            finish_reason = choice.get("finish_reason") or finish_reason
            delta = choice.get("delta") or {}
            if not isinstance(delta, dict):
                raise LocalAIError("GroqCloud returned an invalid stream delta.", code="invalid_response")
            if delta.get("content"):
                content += str(delta["content"])
                if on_text and len(content) - last_visible >= 18:
                    on_text(content)
                    last_visible = len(content)
            for tool in delta.get("tool_calls") or []:
                if not isinstance(tool, dict):
                    raise LocalAIError("GroqCloud returned invalid stream tool calls.", code="tool_call")
                try:
                    idx = int(tool.get("index", 0))
                except (TypeError, ValueError):
                    raise LocalAIError("GroqCloud returned an invalid tool index.", code="tool_call") from None
                c = calls.setdefault(idx, {"id": "", "name": "", "arguments": ""})
                if tool.get("id"):
                    c["id"] += str(tool["id"])
                fn = tool.get("function") or {}
                if not isinstance(fn, dict):
                    raise LocalAIError("GroqCloud returned an invalid tool function.", code="tool_call")
                if fn.get("name"):
                    c["name"] += str(fn["name"])
                if fn.get("arguments"):
                    c["arguments"] += str(fn["arguments"])
    if on_text and len(content) > last_visible:
        on_text(content)
    if finish_reason == "length":
        raise LocalAIError("GroqCloud reached the response length limit.", code="output_limit")
    if calls and finish_reason != "tool_calls":
        raise LocalAIError("GroqCloud stream ended before completing its tool calls.", code="tool_call")
    raw_calls = []
    for idx, tool in sorted(calls.items()):
        raw_calls.append({
            "id": tool["id"] or f"call_stream_{idx}",
            "type": "function",
            "function": {"name": tool["name"], "arguments": tool["arguments"]},
        })
    return {"content": _strip_reasoning(content).strip(), "tool_calls": _normalize_tool_calls(raw_calls)}


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
            "max_completion_tokens": max(1024, min(int(max_tokens), 4096)),
            "reasoning_effort": "low",
            "stream": True,
        }
        if tools:
            payload["tools"] = tools
            payload["tool_choice"] = "auto"
            payload["parallel_tool_calls"] = False
        status("GroqCloud is handling the request…")
        for output_attempt in range(2):
            try:
                with requests.post(
                    GROQ_API_URL,
                    headers={"Authorization": f"Bearer {key}", "Content-Type": "application/json",
                             "User-Agent": "YourAssistantAgent/2.5"},
                    json=payload, stream=True, timeout=(5, min(max(10, int(timeout)), 22)),
                ) as response:
                    if not response.ok:
                        error = _groq_http_error(response)
                        self._write_log(f"GroqCloud HTTP {response.status_code}; code={error.code}")
                        raise error
                    turn = assemble_stream(response.iter_lines(),
                                           on_text=lambda v: status(PREFIX + v[-2000:]))
                break
            except LocalAIError as exc:
                if exc.code != "output_limit" or output_attempt or payload["max_completion_tokens"] >= 4096:
                    raise
                payload["max_completion_tokens"] = 4096
                self._write_log("GroqCloud output limit reached; retrying before tool execution.")
                status("GroqCloud is completing the tool request…")
            except requests.RequestException as exc:
                raise LocalAIError("GroqCloud connection timed out or failed.", code="network") from exc
        if not turn["content"] and not turn["tool_calls"]:
            raise LocalAIError("GroqCloud stream ended without a usable response.", code="invalid_response")
        self.last_used_monotonic = time.monotonic()
        return turn

    LocalAIRuntime.native_turn = native_turn
    _APPLIED = True
