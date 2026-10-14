import json
from pathlib import Path

from your_assistant_agent.agent_brain import AgentBrain
from your_assistant_agent.local_ai_runtime import LocalAIRuntime


class DummyDB:
    def __init__(self, settings=None):
        self.settings = settings or {}
    def get_setting(self, key, default=None):
        return self.settings.get(key, default)


class DummySecurity:
    def get_secret(self, key):
        return ""


def test_local_json_extraction_with_think_and_fence():
    text = '<think>hidden reasoning</think>\n```json\n{"intent":"conversation","reply":"تمام"}\n```'
    got = LocalAIRuntime.extract_json_object(text)
    assert got["intent"] == "conversation"
    assert got["reply"] == "تمام"


def test_brain_defaults_to_free_local_provider():
    brain = AgentBrain(DummyDB(), DummySecurity(), "ar")
    assert brain.enabled is True
    assert brain.provider == "local"


def test_non_campaign_intent_never_creates_rule():
    brain = AgentBrain(DummyDB(), DummySecurity(), "ar")
    out = brain._payload_to_interpretation(
        {
            "intent": "status",
            "needs_clarification": False,
            "question": "",
            "reply": "الوكيل يعمل",
            "understanding": "المستخدم يسأل عن الحالة",
            "confidence": 0.9,
            "plans": [],
        },
        "شو الوضع؟",
        "https://www.facebook.com/source",
        60,
        100,
        14,
        "local_ai",
    )
    assert out.intent == "status"
    assert out.plans == []
    assert out.reply == "الوكيل يعمل"


def test_filtered_campaign_cannot_silently_be_all_groups():
    brain = AgentBrain(DummyDB(), DummySecurity(), "ar")
    try:
        brain._payload_to_interpretation(
            {
                "intent": "campaign",
                "needs_clarification": False,
                "question": "",
                "reply": "",
                "understanding": "جروبات محددة",
                "confidence": 0.9,
                "plans": [{
                    "name": "x",
                    "source_page_url": "",
                    "schedule_kind": "recurring",
                    "run_time": "20:00",
                    "run_once_at": "",
                    "weekdays": [],
                    "post_mode": "fixed",
                    "post_offset": 0,
                    "group_keyword": "",
                    "all_groups": False,
                    "max_groups": 100,
                    "interval_seconds": 60,
                    "no_repeat_days": 14,
                }],
            },
            "على الجروبات اللي إلها علاقة بخلدة",
            "https://www.facebook.com/source",
            60, 100, 14, "local_ai",
        )
    except Exception as exc:
        assert "فلترة" in str(exc) or "filter" in str(exc).lower()
    else:
        raise AssertionError("unsafe plan should have been rejected")
