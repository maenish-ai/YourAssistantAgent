import requests

from yaa_lite.ai.profiles import HAMMER
from yaa_lite.ai.runtime import LocalAIRuntime


def test_runtime_retries_once_in_safe_mode(monkeypatch):
    runtime = LocalAIRuntime(context_tokens=768, threads=2, retry_once=True)
    calls = []
    stops = []

    def fake_post(profile, messages, max_tokens, timeout, status, safe_mode, tools=None):
        calls.append(safe_mode)
        if not safe_mode:
            raise requests.ConnectionError("connection dropped")
        return {"content": "تم"}

    monkeypatch.setattr(runtime, "_post_completion", fake_post)
    monkeypatch.setattr(runtime, "stop", lambda wait=True: stops.append(wait))
    monkeypatch.setattr(runtime, "_write_log", lambda message: None)

    result = runtime.chat(HAMMER, [], 128, 30)
    assert result == "تم"
    assert calls == [False, True]
    assert stops == [True]


def test_runtime_configuration_is_capped_for_4gb():
    runtime = LocalAIRuntime(context_tokens=4096, threads=16)
    assert runtime.context_tokens == 1024
    assert runtime.threads == 2
