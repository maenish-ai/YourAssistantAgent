import json
from pathlib import Path

from yaa_lite.agent.hammer_agent import HAMMER_MODEL_LABEL, HammerAgentRouter
from yaa_lite.ai.profiles import HAMMER, get_profile
from yaa_lite.config import Settings

ROOT = Path(__file__).resolve().parents[1]


class FakeRuntime:
    def __init__(self, response=None):
        self.response = response or {"name": "respond", "arguments": {"message": "hello"}, "content": ""}
        self.last_tools = None

    def tool_call(self, profile, messages, tools, max_tokens, timeout, status=None):
        self.last_tools = tools
        return self.response


def test_only_hammer_model_is_shipped_in_manifest():
    data = json.loads((ROOT / "models.manifest.json").read_text(encoding="utf-8"))
    assert len(data["models"]) == 1
    model = data["models"][0]
    assert model["key"] == "hammer"
    assert "Hammer2.1" in model["base_model"]
    assert model["filename"] == "hammer2.1-0.5b-Q4_K_M.gguf"
    assert model["sha256"] == "190676fe7ac430ac6680b32c216d4eb7413002e2af0c140b8280a0f74fcc6a4d"
    assert model["license"] == "CC-BY-NC-4.0"


def test_old_visible_profiles_resolve_to_same_hammer_model():
    assert get_profile("arabic").model_filename == HAMMER.model_filename
    assert get_profile("general").model_filename == HAMMER.model_filename
    assert get_profile("hammer").model_filename == HAMMER.model_filename


def test_hammer_router_exposes_safe_tools_and_respond():
    rt = FakeRuntime()
    router = HammerAgentRouter(rt)
    result = router.decide([], "كيف حالك", 128, 10)
    assert result.name == "respond"
    names = {x["function"]["name"] for x in rt.last_tools}
    assert "respond" in names
    assert "prepare_facebook_campaign" in names
    assert "discover_facebook_groups" in names
    assert "run_facebook_rule_now" in names
    assert "python" not in " ".join(names).lower()


def test_settings_default_to_single_hammer_agent_and_bilingual_ui():
    s = Settings()
    assert s.selected_agent == "hammer"
    assert s.interface_language == "bilingual"
    assert s.smart_agent_framework == "hammer2.1-tool-router"
    assert "Hammer 2.1" in HAMMER_MODEL_LABEL


def test_status_page_has_live_facebook_progress_events():
    activity = (ROOT / "src" / "yaa_lite" / "ui" / "activity_view.py").read_text(encoding="utf-8")
    service = (ROOT / "src" / "yaa_lite" / "agent" / "facebook_service.py").read_text(encoding="utf-8")
    assert "facebook_group_share_start" in activity
    assert "facebook_group_share_start" in service
    assert "facebook_source_post_search" in service
    assert "facebook_post_found" in service


def test_runtime_normalizes_hammer_text_json(monkeypatch):
    from yaa_lite.ai.runtime import LocalAIRuntime
    rt = LocalAIRuntime(retry_once=False)
    monkeypatch.setattr(rt, "_post_completion", lambda *a, **k: {"content": '```\n{"name":"count_facebook_groups","arguments":{"keyword":"خلدة"}}\n```'})
    out = rt.tool_call(HAMMER, [], HammerAgentRouter.tool_schemas(), 128, 10)
    assert out["name"] == "count_facebook_groups"
    assert out["arguments"]["keyword"] == "خلدة"


def test_runtime_normalizes_openai_tool_calls(monkeypatch):
    from yaa_lite.ai.runtime import LocalAIRuntime
    rt = LocalAIRuntime(retry_once=False)
    monkeypatch.setattr(rt, "_post_completion", lambda *a, **k: {
        "content": None,
        "tool_calls": [{"function": {"name": "facebook_status", "arguments": "{}"}}],
    })
    out = rt.tool_call(HAMMER, [], HammerAgentRouter.tool_schemas(), 128, 10)
    assert out["name"] == "facebook_status"
