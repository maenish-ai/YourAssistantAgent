import json
from pathlib import Path

from yaa_lite.agent.hammer_agent import PRIMARY_MODEL_LABEL
from yaa_lite.ai.profiles import QWEN, HAMMER, get_profile
from yaa_lite.config import Settings

ROOT = Path(__file__).resolve().parents[1]


def test_only_qwen_model_is_shipped_in_manifest():
    data = json.loads((ROOT / "models.manifest.json").read_text(encoding="utf-8"))
    assert len(data["models"]) == 1
    model = data["models"][0]
    assert model["key"] == "qwen"
    assert model["base_model"] == "Qwen/Qwen3-1.7B"
    assert model["filename"] == "Qwen3-1.7B-Q4_K_M.gguf"
    assert model["sha256"] == "d2387ca2dbfee2ffabce7120d3770dadca0b293052bc2f0e138fdc940d9bc7b5"
    assert model["license"] == "Apache-2.0"


def test_old_profile_aliases_resolve_to_qwen_model():
    assert get_profile("arabic").model_filename == QWEN.model_filename
    assert get_profile("general").model_filename == QWEN.model_filename
    assert get_profile("hammer").model_filename == QWEN.model_filename
    assert HAMMER.model_filename == QWEN.model_filename


def test_primary_personal_agent_has_no_respond_tool():
    from yaa_lite.personal_assistant_v220 import _tool_schemas
    names = {x["function"]["name"] for x in _tool_schemas()}
    assert "respond" not in names
    assert {"discover_facebook_groups", "search_facebook_groups", "draft_facebook_campaign"} <= names
    assert "python" not in " ".join(names).lower()


def test_settings_default_to_qwen_and_voice_ready():
    s = Settings()
    assert s.selected_agent == "qwen"
    assert s.interface_language in {"ar", "en"}
    assert s.smart_agent_framework == "qwen3-1.7b-primary-agent"
    assert s.hammer_retry_count == 2
    assert s.hammer_idle_minutes == 0
    assert s.voice_enabled
    assert "Qwen3" in PRIMARY_MODEL_LABEL


def test_runtime_uses_jinja_for_qwen_native_tools():
    runtime = (ROOT / "src" / "yaa_lite" / "ai" / "runtime.py").read_text(encoding="utf-8")
    assert '"--jinja"' in runtime
    assert 'payload["tools"] = tools' in runtime
    assert 'payload["tool_choice"] = "auto"' in runtime
    assert 'payload["parallel_tool_calls"] = False' in runtime


def test_runtime_tool_call_is_legacy_adapter_over_native_turn(monkeypatch):
    from yaa_lite.ai.runtime import LocalAIRuntime
    rt = LocalAIRuntime(retry_count=0, prewarm=False)
    monkeypatch.setattr(rt, "native_turn", lambda *a, **k: {
        "content": "",
        "tool_calls": [{"name": "facebook_status", "arguments": {}, "id": "call1"}],
    })
    out = rt.tool_call(QWEN, [], [], 128, 10)
    assert out["name"] == "facebook_status"
    assert out["arguments"] == {}


def test_runtime_tool_call_legacy_adapter_maps_plain_text_to_respond(monkeypatch):
    from yaa_lite.ai.runtime import LocalAIRuntime
    rt = LocalAIRuntime(retry_count=0, prewarm=False)
    monkeypatch.setattr(rt, "native_turn", lambda *a, **k: {
        "content": "أهلًا! كيف أقدر أساعدك؟", "tool_calls": []
    })
    out = rt.tool_call(QWEN, [], [], 128, 10)
    assert out["name"] == "respond"
    assert "أساعدك" in out["arguments"]["message"]


def test_runtime_chat_uses_normal_chat_completion(monkeypatch):
    from yaa_lite.ai.runtime import LocalAIRuntime
    rt = LocalAIRuntime(retry_count=0, prewarm=False)
    monkeypatch.setattr(rt, "_chat_completion", lambda *a, **k: "تمام، الحمد لله")
    out = rt.chat(QWEN, [{"role":"user","content":"كيف حالك"}], 128, 10)
    assert out == "تمام، الحمد لله"
