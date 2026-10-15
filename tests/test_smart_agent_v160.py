from pathlib import Path

from yaa_lite.agent.facebook_service import FacebookService
from yaa_lite.agent.orchestrator import SmartAgentController
from yaa_lite.agent.tools import ToolRegistry
from yaa_lite.ai.engine import ChatEngine
from yaa_lite.ai.profiles import get_profile
from yaa_lite.config import Settings
from yaa_lite.storage.db import ChatDB


class RuntimeShouldNotRun:
    def chat(self, *a, **k):
        raise AssertionError("local model should not be needed for this test")


def make_controller(tmp_path):
    db = ChatDB(tmp_path / "assistant.sqlite3")
    db.upsert_groups([
        {"name": "خلدة وأم السماق", "url": "https://facebook.com/groups/1"},
        {"name": "سكان خلدة", "url": "https://facebook.com/groups/2"},
        {"name": "صويلح اليوم", "url": "https://facebook.com/groups/3"},
    ])
    settings = Settings(
        selected_agent="arabic",
        smart_agent_enabled=True,
        confirm_external_actions=True,
        default_source_page="https://www.facebook.com/source-page",
    )
    facebook = FacebookService(db, settings)
    controller = SmartAgentController(db, settings, ChatEngine(RuntimeShouldNotRun()), facebook)
    return db, controller, facebook, settings


def test_greeting_stays_real_chat(tmp_path):
    db, controller, facebook, settings = make_controller(tmp_path)
    sid = db.create_session("arabic")
    reply = controller.handle(get_profile("arabic"), [], "كيف حالك؟", sid, 128, 10)
    assert "جاهز" in reply.text
    assert not reply.used_tools
    facebook.shutdown()


def test_natural_facebook_instruction_previews_and_counts_groups(tmp_path):
    db, controller, facebook, settings = make_controller(tmp_path)
    sid = db.create_session("arabic")
    reply = controller.handle(
        get_profile("arabic"),
        [],
        "غداً الساعة 8 مساء شارك آخر منشور على جميع المجموعات التي يوجد في اسمها كلمة خلدة",
        sid,
        128,
        10,
    )
    assert "المجموعات المطابقة" in reply.text
    assert "2" in reply.text
    pending = db.get_pending_action(sid)
    assert pending and pending["tool_name"] == "save_facebook_share_rule"
    assert pending["arguments"]["group_keyword"] == "خلدة"
    facebook.shutdown()


def test_followup_edit_then_approve_saves_rule(tmp_path):
    db, controller, facebook, settings = make_controller(tmp_path)
    sid = db.create_session("arabic")
    controller.handle(
        get_profile("arabic"), [],
        "غداً الساعة 8 مساء شارك آخر منشور على المجموعات التي في اسمها خلدة",
        sid, 128, 10,
    )
    edited = controller.handle(get_profile("arabic"), [], "خليها الساعة 9", sid, 128, 10)
    assert "21:00" in edited.text
    approved = controller.handle(get_profile("arabic"), [], "نعم", sid, 128, 10)
    assert "تم حفظ المهمة" in approved.text
    rules = db.list_rules()
    assert len(rules) == 1
    assert rules[0]["run_time"] == "21:00"
    facebook.shutdown()


def test_tool_registry_is_allowlisted_and_smolagents_dependency_is_declared(tmp_path):
    db, controller, facebook, settings = make_controller(tmp_path)
    tools = ToolRegistry(db, facebook)
    assert "save_facebook_share_rule" in tools.tools
    assert "discover_facebook_groups" in tools.tools
    root = Path(__file__).resolve().parents[1]
    contract = (root / "src" / "yaa_lite" / "agent" / "smol_contract.py").read_text(encoding="utf-8")
    assert "huggingface/smolagents" in contract
    assert (root / "licenses" / "Apache-2.0-smolagents.txt").exists()
    facebook.shutdown()
