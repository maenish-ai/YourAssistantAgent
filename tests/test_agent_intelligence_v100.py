from datetime import datetime

from your_assistant_agent.agent_brain import AgentBrain
from your_assistant_agent.db import Database
from your_assistant_agent.share_outcome import classify_share_result_text
from your_assistant_agent.smart_agent import SmartPlanner


class DummyDB:
    def get_setting(self, key, default=None):
        return default


class DummySecurity:
    def get_secret(self, name):
        return ""


def test_local_parser_handles_arbitrary_group_name_phrase():
    planner = SmartPlanner("ar")
    plan = planner.parse(
        "اليوم الساعة 8 مساء انشر آخر منشور على الجروبات اللي فيها دابوق",
        "https://www.facebook.com/example",
    )
    assert plan.group_keyword == "دابوق"
    assert plan.run_time == "20:00"
    assert plan.post_offset == 0
    assert plan.run_once_at


def test_ai_payload_becomes_safe_plan():
    brain = AgentBrain(DummyDB(), DummySecurity(), "ar")
    payload = {
        "needs_clarification": False,
        "question": "",
        "understanding": "انشر آخر منشور على جروبات خلدة غدًا الساعة 8 مساء",
        "confidence": 0.97,
        "plans": [{
            "name": "خلدة غدًا",
            "source_page_url": "",
            "schedule_kind": "once",
            "run_time": "20:00",
            "run_once_at": "2099-01-01T20:00:00",
            "weekdays": [],
            "post_mode": "fixed",
            "post_offset": 0,
            "group_keyword": "خلدة",
            "all_groups": False,
            "max_groups": 100,
            "interval_seconds": 60,
            "no_repeat_days": 14,
        }],
    }
    result = brain._payload_to_interpretation(
        payload,
        "الأمر",
        "https://www.facebook.com/source",
        60,
        100,
        14,
    )
    assert result.source == "ai"
    assert result.confidence == 0.97
    assert result.plans[0].group_keyword == "خلدة"
    assert result.plans[0].source_page_url.endswith("/source")


def test_ai_clarification_does_not_create_plan():
    brain = AgentBrain(DummyDB(), DummySecurity(), "ar")
    result = brain._payload_to_interpretation(
        {
            "needs_clarification": True,
            "question": "تقصد كل الجروبات ولا الجروبات التي فيها خلدة؟",
            "understanding": "الهدف غير واضح",
            "confidence": 0.45,
            "plans": [],
        },
        "انشر عليهم",
        "https://www.facebook.com/source",
        60,
        100,
        14,
    )
    assert result.needs_clarification is True
    assert not result.plans


def test_pending_admin_approval_is_classified_as_success_state():
    assert classify_share_result_text("Your post is pending admin approval") == "pending_approval"
    assert classify_share_result_text("تم إرسال منشورك للمراجعة من قبل المشرف") == "pending_approval"
    assert classify_share_result_text("Your post was shared") == "published"
    assert classify_share_result_text("") == "submitted"


def test_pending_approval_prevents_duplicate_resend(tmp_path):
    db = Database(tmp_path / "agent.db")
    gid = db.add_group("خلدة Test", "https://www.facebook.com/groups/123", "خلدة")
    # add_group returns sqlite lastrowid in the current implementation
    if gid is None:
        gid = db.list_groups(enabled_only=True, keyword="خلدة", limit=1)[0]["id"]
    db.record_share(None, int(gid), "https://www.facebook.com/post/1", "pending_approval")
    assert db.was_shared_recently(int(gid), "https://www.facebook.com/post/1", 14)
