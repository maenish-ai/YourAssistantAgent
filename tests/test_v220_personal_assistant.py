import json
from pathlib import Path

from yaa_lite.personal_assistant_v220 import (
    FILTER_PREFIX,
    decode_group_filter,
    encode_group_filter,
    _tool_schemas,
)

ROOT = Path(__file__).resolve().parents[1]


def test_structured_group_filter_preserves_include_and_exact_exclusion():
    encoded = encode_group_filter(["الفحص"], [], ["الفحص التجارية"], "any")
    assert encoded.startswith(FILTER_PREFIX)
    data = decode_group_filter(encoded)
    assert data["include_keywords"] == ["الفحص"]
    assert data["exclude_names"] == ["الفحص التجارية"]
    assert data["match_mode"] == "any"


def test_direct_personal_agent_tool_list_has_no_fake_respond():
    names = {tool["function"]["name"] for tool in _tool_schemas()}
    assert "respond" not in names
    assert "open_facebook_login" in names
    assert "verify_facebook_connection" in names
    assert "discover_facebook_groups" in names
    assert "search_facebook_groups" in names
    assert "draft_facebook_campaign" in names


def test_launcher_applies_personal_assistant_layer_before_main():
    launcher = (ROOT / "launcher.py").read_text(encoding="utf-8")
    bootstrap = (ROOT / "src/yaa_lite/bootstrap.py").read_text(encoding="utf-8")
    main = (ROOT / "src/yaa_lite/main.py").read_text(encoding="utf-8")
    assert "apply_personal_assistant()" in bootstrap
    assert main.index("configure_application()") < main.index("GroqApp().mainloop()")


def test_personal_controller_has_multistep_cap_and_approval_gate():
    src = (ROOT / "src" / "yaa_lite" / "personal_assistant_v220.py").read_text(encoding="utf-8")
    assert "for _step in range(5)" in src
    assert '"approve_facebook_campaign"' in src
    assert "Preview" in src or "preview" in src
    assert "Passwords" not in src


def test_native_turn_parses_openai_style_cloud_tool_call(monkeypatch):
    from yaa_lite.ai.profiles import QWEN
    from yaa_lite.ai.runtime import LocalAIRuntime
    import yaa_lite.ai.runtime as runtime_module

    monkeypatch.setenv("GROQ_API_KEY", "test-only-key")

    class Resp:
        ok = True
        status_code = 200
        text = ""
        def raise_for_status(self): return None
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
        seen["payload"] = json
        return Resp()

    rt = LocalAIRuntime(retry_count=0, prewarm=False)
    monkeypatch.setattr(runtime_module.requests, "post", fake_post)
    turn = rt.native_turn(QWEN, [{"role":"user","content":"افحص فيسبوك"}], _tool_schemas(), 128, 10)
    assert turn["tool_calls"][0]["name"] == "facebook_status"
    assert seen["url"].endswith("/openai/v1/chat/completions")
    assert seen["payload"]["model"] == "openai/gpt-oss-120b"
    assert seen["payload"]["tool_choice"] == "auto"
    assert seen["payload"]["parallel_tool_calls"] is False
