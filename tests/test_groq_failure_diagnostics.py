"""Offline regressions for real Groq payload/stream and launch-wrapper paths."""
import json
import os
from pathlib import Path
import subprocess
import sys

import pytest
import requests

from yaa_lite.ai.runtime import LocalAIError, LocalAIRuntime, _compact_native_messages
from yaa_lite.fast_stream_v250 import assemble_stream


def exchange(identifier, arguments=None, result="found page"):
    return [
        {"role": "assistant", "content": "", "tool_calls": [{
            "id": identifier, "type": "function",
            "function": {"name": "search_facebook_pages", "arguments": json.dumps(arguments or {"query": "سوريا"})},
            "name": "search_facebook_pages", "arguments": arguments or {"query": "سوريا"},
        }]},
        {"role": "tool", "tool_call_id": identifier, "content": result},
    ]


def assert_complete_tool_exchanges(rows):
    waiting = set()
    for row in rows:
        if row["role"] == "tool":
            assert row["tool_call_id"] in waiting
            waiting.remove(row["tool_call_id"])
        else:
            assert not waiting
            waiting = {call["id"] for call in row.get("tool_calls", [])}
            for call in row.get("tool_calls", []):
                assert set(call) == {"id", "type", "function"}
    assert not waiting


@pytest.mark.parametrize("slots", [1, 2, 3, 4, 5, 6])
def test_compaction_never_orphans_tool_results_and_keeps_current_request(slots):
    current = {"role": "user", "content": "Find latest post and groups containing Syria"}
    rows = _compact_native_messages([
        {"role": "system", "content": "Use actual page URLs"},
        {"role": "user", "content": "old request"}, *exchange("old"), current,
        *exchange("new"),
    ], max_messages=slots)
    assert current in rows
    assert len(rows) <= slots
    assert_complete_tool_exchanges(rows)


@pytest.mark.parametrize("budget", [0, 1, 30, 100, 300, 1000])
def test_compaction_counts_tool_arguments_and_handles_zero_remaining_budget(budget):
    rows = _compact_native_messages([
        {"role": "system", "content": "s" * 100},
        {"role": "user", "content": "u" * 20},
        *exchange("large", {"query": "x" * 2000}, "z" * 2000),
    ], total_chars=budget)
    used = sum(len(row["content"]) + len(row.get("tool_call_id", "")) +
               (len(json.dumps(row["tool_calls"], ensure_ascii=False)) if row.get("tool_calls") else 0)
               for row in rows)
    assert used <= budget
    assert_complete_tool_exchanges(rows)


def test_compaction_discards_incomplete_multi_call_exchange():
    block = exchange("first")
    block[0]["tool_calls"] += exchange("missing")[0]["tool_calls"]
    rows = _compact_native_messages([{"role": "user", "content": "request"}, *block])
    assert rows == [{"role": "user", "content": "request"}]


@pytest.mark.parametrize("arguments", ['{"query":', "[]", '"text"', "null"])
def test_stream_rejects_malformed_tool_json_instead_of_executing_empty_arguments(arguments):
    lines = ['data: ' + json.dumps({"choices": [{"delta": {"tool_calls": [{
        "index": 0, "id": "call_1", "function": {"name": "draft_facebook_campaign", "arguments": arguments},
    }]}}]}), "data: [DONE]"]
    with pytest.raises(LocalAIError) as error:
        assemble_stream(lines)
    assert error.value.code == "tool_call"


def test_stream_distinguishes_output_limit_before_parsing_partial_tool_json():
    lines = ['data: ' + json.dumps({"choices": [{"delta": {"tool_calls": [{
        "index": 0, "id": "call_1", "function": {"name": "draft_facebook_campaign", "arguments": '{"query":'},
    }]}, "finish_reason": "length"}]}), "data: [DONE]"]
    with pytest.raises(LocalAIError) as error:
        assemble_stream(lines)
    assert error.value.code == "output_limit"


@pytest.mark.parametrize("terminal", [[], ["data: [DONE]"]])
def test_stream_rejects_valid_looking_tool_arguments_without_terminal_choice(terminal):
    lines = ['data: ' + json.dumps({"choices": [{"delta": {"tool_calls": [{
        "index": 0, "id": "call_1", "function": {"name": "draft_facebook_campaign", "arguments": '{}'},
    }]}}]}), *terminal]
    with pytest.raises(LocalAIError) as error:
        assemble_stream(lines)
    assert error.value.code == "tool_call"


def test_stream_accepts_terminal_tool_choice_without_done_marker():
    lines = ['data: ' + json.dumps({"choices": [{"delta": {"tool_calls": [{
        "index": 0, "id": "call_1", "function": {"name": "search_facebook_pages", "arguments": '{"query":"Syria"}'},
    }]}, "finish_reason": "tool_calls"}]})]
    assert assemble_stream(lines)['tool_calls'][0]['arguments'] == {"query": "Syria"}


def test_network_retry_does_not_log_raw_exception_credentials(monkeypatch):
    import yaa_lite.ai.runtime as module
    monkeypatch.setattr(module, "get_groq_api_key", lambda required=True: "test-only")
    runtime = LocalAIRuntime(retry_count=0)
    logs = []
    monkeypatch.setattr(runtime, "_write_log", logs.append)

    def fail(_):
        raise requests.ConnectionError("https://user:SECRET@host/?token=SECRET")

    with pytest.raises(LocalAIError) as error:
        runtime._run_with_retry(fail)
    assert error.value.code == "network"
    assert "SECRET" not in str(error.value) + " ".join(logs)


def test_configured_application_covers_mobile_and_streamed_failures(tmp_path):
    # A fresh interpreter ensures configure_application applies the same full
    # monkey-patch stack used by Windows; no GUI or account is required.
    script = r'''
import json
from unittest.mock import patch
import requests
from yaa_lite.bootstrap import configure_application
configure_application()
from yaa_lite.ai.runtime import LocalAIError, LocalAIRuntime
from yaa_lite.ai.profiles import QWEN

class Response:
    def __init__(self, status=200, payload=None):
        self.status_code = status
        self.ok = status == 200
        self.payload = payload
        self.text = "SECRET_RAW_GENERATION"
    def __enter__(self): return self
    def __exit__(self, *args): pass
    def json(self): return self.payload
    def iter_lines(self):
        if self.payload and self.payload.get("choices"):
            choice = self.payload["choices"][0]
            yield "data: " + json.dumps({"choices": [{"delta": choice["message"], "finish_reason": choice.get("finish_reason")}]})
        yield "data: [DONE]"

def completion(arguments='{"query":"سوريا"}', finish="tool_calls"):
    return {"choices": [{"finish_reason": finish, "message": {"content": "", "tool_calls": [{
        "id": "call_1", "index": 0, "type": "function",
        "function": {"name": "search_facebook_pages", "arguments": arguments},
    }]}}]}

tools = [{"type": "function", "function": {"name": "search_facebook_pages", "parameters": {"type": "object", "properties": {"query": {"type": "string"}}}}}]
messages = [{"role": "user", "content": "ابحث عن صفحة ومجموعات سوريا"}]
logs = []
with patch("yaa_lite.ai.runtime.get_groq_api_key", return_value="offline-test-key"), patch("yaa_lite.fast_stream_v250.get_groq_api_key", return_value="offline-test-key"):
    rt = LocalAIRuntime(retry_count=0)
    rt._write_log = logs.append
    for status in (None, lambda text: None):
        def invoke():
            return rt.native_turn(QWEN, messages, tools, max_tokens=128, timeout=20, status=status)

        for http, error_code, expected in [(401, None, "auth"), (403, None, "auth"), (429, None, "rate_limit"), (503, None, "service_unavailable"), (400, "tool_use_failed", "tool_call"), (400, None, "request_rejected")]:
            with patch("requests.post", return_value=Response(http, {"error": {"code": error_code, "message": "SECRET_RAW_GENERATION"}})):
                try:
                    invoke()
                    raise AssertionError("Expected safe error")
                except LocalAIError as exc:
                    assert exc.code == expected, (http, exc.code, expected)
                    assert "SECRET" not in str(exc)

        with patch("requests.post", side_effect=requests.ConnectionError("SECRET_RAW_GENERATION")):
            try:
                invoke()
                raise AssertionError("Expected network error")
            except LocalAIError as exc:
                assert exc.code == "network"

        with patch("requests.post", return_value=Response(payload=completion('{"query":'))):
            try:
                invoke()
                raise AssertionError("Partial arguments must never execute")
            except LocalAIError as exc:
                assert exc.code == "tool_call"

        payloads = []
        def recover(*args, **kwargs):
            payloads.append(dict(kwargs["json"]))
            return Response(payload=completion('{"query":', "length") if len(payloads) == 1 else completion())
        with patch("requests.post", side_effect=recover):
            turn = invoke()
            assert turn["tool_calls"][0]["arguments"] == {"query": "سوريا"}
            assert [item["max_completion_tokens"] for item in payloads] == [1024, 4096]
            assert all(item["reasoning_effort"] == "low" for item in payloads)

        with patch("requests.post", return_value=Response(payload=completion('{"query":', "length"))) as post:
            try:
                invoke()
                raise AssertionError("Expected bounded output limit")
            except LocalAIError as exc:
                assert exc.code == "output_limit"
                assert post.call_count == 2
assert not any("SECRET" in entry for entry in logs)
'''
    root = Path(__file__).resolve().parents[1]
    result = subprocess.run([sys.executable, "-c", script], cwd=root,
                            env={**os.environ, "PYTHONPATH": str(root / "src"), "XDG_DATA_HOME": str(tmp_path)},
                            capture_output=True, text=True, timeout=30)
    assert result.returncode == 0, result.stdout + result.stderr
