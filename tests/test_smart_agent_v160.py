from pathlib import Path

from yaa_lite.agent.facebook_service import FacebookService
from yaa_lite.agent.orchestrator import SmartAgentController
from yaa_lite.agent.tools import ToolRegistry
from yaa_lite.ai.engine import ChatEngine
from yaa_lite.ai.profiles import HAMMER
from yaa_lite.config import Settings
from yaa_lite.storage.db import ChatDB


class FakeRuntime:
    def __init__(self, decisions):
        self.decisions=list(decisions)
        self.chat_calls=[]
    def tool_call(self,*a,**k):
        return self.decisions.pop(0)
    def chat(self,profile,messages,max_tokens,timeout,status=None):
        self.chat_calls.append(messages)
        return "تمت العملية."


def make_controller(tmp_path, decisions):
    db=ChatDB(tmp_path/"assistant.sqlite3")
    db.upsert_groups([
        {"name":"خلدة وأم السماق","url":"https://facebook.com/groups/1"},
        {"name":"سكان خلدة","url":"https://facebook.com/groups/2"},
        {"name":"صويلح اليوم","url":"https://facebook.com/groups/3"},
    ])
    settings=Settings(smart_agent_enabled=True,confirm_external_actions=True,default_source_page="https://www.facebook.com/source-page")
    facebook=FacebookService(db,settings)
    runtime=FakeRuntime(decisions)
    controller=SmartAgentController(db,settings,ChatEngine(runtime),facebook)
    return db,controller,facebook,runtime


def test_greeting_is_decided_by_hammer_not_a_keyword_router(tmp_path):
    db,controller,facebook,runtime=make_controller(tmp_path,[{"name":"respond","arguments":{"message":"أنا تمام 😄"},"content":""}])
    sid=db.create_session("hammer")
    reply=controller.handle(HAMMER,[],"كيف حالك؟",sid,128,10)
    assert "تمام" in reply.text and reply.used_model and not reply.used_tools
    facebook.shutdown()


def test_hammer_selects_facebook_planner_then_app_previews(tmp_path):
    decision={"name":"prepare_facebook_campaign","arguments":{"instruction":"غداً الساعة 8 مساء شارك آخر منشور على جميع المجموعات التي يوجد في اسمها كلمة خلدة"},"content":""}
    db,controller,facebook,runtime=make_controller(tmp_path,[decision])
    sid=db.create_session("hammer")
    reply=controller.handle(HAMMER,[],decision["arguments"]["instruction"],sid,128,10)
    assert "2" in reply.text
    pending=db.get_pending_action(sid)
    assert pending and pending["tool_name"]=="save_facebook_share_rule"
    assert pending["arguments"]["group_keyword"]=="خلدة"
    facebook.shutdown()


def test_approval_gate_is_deterministic_and_executes_allowlisted_tool(tmp_path):
    decision={"name":"prepare_facebook_campaign","arguments":{"instruction":"غداً الساعة 8 مساء شارك آخر منشور على المجموعات التي في اسمها خلدة"},"content":""}
    db,controller,facebook,runtime=make_controller(tmp_path,[decision])
    sid=db.create_session("hammer")
    controller.handle(HAMMER,[],decision["arguments"]["instruction"],sid,128,10)
    approved=controller.handle(HAMMER,[],"نعم",sid,128,10)
    assert db.get_pending_action(sid) is None
    assert len(db.list_rules())==1
    assert approved.used_tools
    facebook.shutdown()


def test_tool_registry_is_allowlisted_and_smolagents_contract_is_kept(tmp_path):
    db,controller,facebook,runtime=make_controller(tmp_path,[])
    tools=ToolRegistry(db,facebook)
    assert "save_facebook_share_rule" in tools.tools
    assert "discover_facebook_groups" in tools.tools
    root=Path(__file__).resolve().parents[1]
    contract=(root/"src"/"yaa_lite"/"agent"/"smol_contract.py").read_text(encoding="utf-8")
    assert "huggingface/smolagents" in contract
    assert (root/"licenses"/"Apache-2.0-smolagents.txt").exists()
    facebook.shutdown()
