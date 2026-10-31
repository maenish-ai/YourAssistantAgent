import json

from yaa_lite.ai.profiles import QWEN
from yaa_lite.ai.runtime import GROQ_MODEL, LocalAIRuntime
import yaa_lite.ai.runtime as runtime_module


def test_cloud_runtime_uses_gpt_oss_and_openai_tool_shape(monkeypatch):
    monkeypatch.setenv("GROQ_API_KEY", "test-key-not-real")

    class Resp:
        ok = True
        status_code = 200
        text = ""
        def json(self):
            return {"choices": [{"message": {
                "role": "assistant",
                "content": "",
                "tool_calls": [{
                    "id": "call_1",
                    "type": "function",
                    "function": {"name": "facebook_status", "arguments": "{}"},
                }],
            }}]}

    seen = {}
    def fake_post(url, headers=None, json=None, timeout=None, **kwargs):
        seen["url"] = url
        seen["headers"] = headers
        seen["payload"] = json
        return Resp()

    monkeypatch.setattr(runtime_module.requests, "post", fake_post)
    rt = LocalAIRuntime(retry_count=0, prewarm=False)
    turn = rt.native_turn(
        QWEN,
        [{"role": "user", "content": "افحص فيسبوك"}],
        [{"type": "function", "function": {
            "name": "facebook_status",
            "description": "status",
            "parameters": {"type": "object", "properties": {}, "required": []},
        }}],
        128,
        10,
    )

    assert GROQ_MODEL == "openai/gpt-oss-120b"
    assert seen["url"].endswith("/openai/v1/chat/completions")
    assert seen["payload"]["model"] == GROQ_MODEL
    assert seen["payload"]["tool_choice"] == "auto"
    assert seen["payload"]["parallel_tool_calls"] is False
    assert turn["tool_calls"][0]["name"] == "facebook_status"
    assert seen["headers"]["Authorization"].startswith("Bearer ")
