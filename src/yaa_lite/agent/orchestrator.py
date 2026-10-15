from __future__ import annotations

import re
from dataclasses import dataclass

from ..ai.engine import ChatEngine, quick_reply
from ..ai.profiles import AgentProfile, HAMMER
from ..config import Settings
from ..storage.db import ChatDB
from .facebook_service import FacebookService
from .hammer_agent import HAMMER_MODEL_LABEL, HammerAgentRouter
from .legacy_smart import SmartPlan, SmartPlanner, SmartPlannerError
from .tools import ToolRegistry


@dataclass
class AgentResponse:
    text: str
    used_model: bool = False
    used_tools: bool = False


_CONFIRM_RE = re.compile(r"^(?:نعم|اه|آه|اوافق|أوافق|وافق|موافق|تمام|نفذ|نفّذ|اعتمد|yes|ok|okay|confirm|approve)$", re.I)
_CANCEL_RE = re.compile(r"^(?:لا|الغ|ألغي|الغاء|إلغاء|بلاش|cancel|no|stop)$", re.I)
_ACTION_RE = re.compile(
    r"(?:انشر|نشر|شارك|مشاركة|وزع|وزّع|ارسل|أرسل|ابعث|ابعت|جدول|جدولة|الساعة|اليوم|غدا|غداً|بكرا|"
    r"جروب|جروبات|مجموعة|مجموعات|فيسبوك|facebook|share|publish|post|schedule|groups?|latest\s+post|آخر\s+(?:بوست|منشور|اعلان|إعلان))",
    re.I,
)
_DISCOVER_RE = re.compile(r"(?:اكتشف|اكتشاف|تعرف|تعرّف|حدث|حدّث|refresh|discover).{0,35}(?:جروب|مجموع|groups?)", re.I)
_STATUS_RE = re.compile(r"(?:حالة|وضع|متصل|الاتصال|status|connected).{0,30}(?:فيسبوك|facebook)|(?:فيسبوك|facebook).{0,30}(?:حالة|متصل|status|connected)", re.I)
_COUNT_RE = re.compile(r"(?:كم|عدد|how many|count).{0,35}(?:جروب|مجموع|groups?)", re.I)
_RUN_RULE_RE = re.compile(r"(?:شغل|شغّل|نفذ|نفّذ|run).{0,25}(?:مهمة|قاعدة|rule)\s*(\d+)", re.I)


class SmartAgentController:
    """Single-assistant controller powered by Hammer 2.1.

    Hammer is the dedicated action model and chooses only from an allow-list of
    tools. Ordinary conversation can be returned through Hammer's ``respond``
    function; simple greetings use an instant local fast path so the model does
    not have to load. External mutations remain behind a confirmation gate.
    """

    def __init__(self, db: ChatDB, settings: Settings, chat_engine: ChatEngine, facebook: FacebookService):
        self.db = db
        self.settings = settings
        self.chat_engine = chat_engine
        self.facebook = facebook
        self.tools = ToolRegistry(db, facebook)
        self.hammer = HammerAgentRouter(chat_engine.runtime)

    def update_settings(self, settings: Settings) -> None:
        self.settings = settings
        self.facebook.update_settings(settings)

    @property
    def framework_label(self) -> str:
        return f"{HAMMER_MODEL_LABEL} — allow-listed tool router"

    def _activity(self, kind: str, detail: str, status=None, friendly: str | None = None) -> None:
        self.db.add_activity(kind, detail)
        if status and friendly:
            status(friendly)

    def handle(
        self,
        profile: AgentProfile,
        history: list[dict],
        user_text: str,
        session_id: int,
        max_tokens: int,
        timeout: int,
        status=None,
    ) -> AgentResponse:
        text = (user_text or "").strip()
        normalized = " ".join(text.split())

        # Confirmation/edit flow is deterministic and survives restarts.
        pending = self.db.get_pending_action(session_id)
        if pending:
            if _CANCEL_RE.match(normalized):
                self.db.clear_pending_action(session_id)
                self._activity("agent_action_cancelled", pending.get("summary", ""), status, "تم إلغاء المهمة / Action cancelled")
                return AgentResponse("تمام، ألغيت العملية المعلّقة. / Cancelled the pending action.", used_tools=True)
            if _CONFIRM_RE.match(normalized):
                self._activity("agent_action_confirmed", pending.get("tool_name", ""), status, "تمت الموافقة — جاري التنفيذ / Approved — executing")
                result = self.tools.execute(pending["tool_name"], pending.get("arguments") or {})
                self.db.clear_pending_action(session_id)
                self._activity("agent_action_executed" if result.ok else "agent_action_error", result.text)
                return AgentResponse(result.text, used_tools=True)

            if pending.get("tool_name") == "save_facebook_share_rule":
                try:
                    context = pending.get("arguments") or {}
                    plan = SmartPlanner("ar").parse(
                        text,
                        default_source_page=self.settings.default_source_page,
                        context_plan=context,
                    )
                    return self._preview_plan(plan, session_id, edited=True, status=status)
                except SmartPlannerError:
                    pass

        # Fast conversational replies never load the model.
        instant = quick_reply(text)
        if instant:
            self._activity("chat_fast_reply", text[:300], status, "رد سريع / Quick reply")
            return AgentResponse(instant, used_model=False, used_tools=False)

        if not self.settings.smart_agent_enabled:
            reply = self.chat_engine.reply(HAMMER, history, text, max_tokens, timeout, status=status)
            return AgentResponse(reply.text, used_model=reply.used_model)

        # Hammer gets first chance to understand every non-trivial message.
        self._activity("hammer_analyzing", text[:500], status, "Hammer 2.1 يحلل الطلب / analyzing request")
        decision = None
        try:
            decision = self.hammer.decide(history, text, max_tokens=max_tokens, timeout=timeout, status=status)
            self._activity("hammer_decision", f"tool={decision.name}; args={decision.arguments}")
        except Exception as exc:
            self._activity("hammer_error", f"{type(exc).__name__}: {exc}", status, "تعذر توجيه Hammer — استخدام الخطة الاحتياطية / fallback")

        if decision:
            name = decision.name
            args = decision.arguments or {}
            if name == "respond":
                message = str(args.get("message") or decision.content or "").strip()
                if message:
                    return AgentResponse(message, used_model=True)
            elif name == "facebook_status":
                result = self.tools.execute("facebook_status")
                self._activity("hammer_tool_result", f"facebook_status: {result.text}", status, "تم فحص حالة Facebook / status checked")
                return AgentResponse(result.text, used_tools=True, used_model=True)
            elif name == "count_facebook_groups":
                keyword = str(args.get("keyword") or "").strip()
                result = self.tools.execute("count_facebook_groups", {"keyword": keyword})
                self._activity("hammer_tool_result", f"count_facebook_groups({keyword})={result.text}", status, "تم عد المجموعات / groups counted")
                if keyword:
                    return AgentResponse(f"عدد المجموعات المطابقة لـ «{keyword}»: {result.text}. / Matching groups: {result.text}.", used_tools=True, used_model=True)
                return AgentResponse(f"عدد المجموعات المحفوظة: {result.text}. / Saved groups: {result.text}.", used_tools=True, used_model=True)
            elif name == "discover_facebook_groups":
                summary = "سأفتح جلسة Facebook المحفوظة وأحدّث قائمة المجموعات. هل أوافق؟ / I will open the saved Facebook session and refresh joined groups. Approve?"
                self.db.set_pending_action(session_id, "discover_facebook_groups", {}, summary)
                self._activity("agent_plan_preview", "discover_facebook_groups", status, "بانتظار موافقتك / Waiting for approval")
                return AgentResponse(summary, used_tools=True, used_model=True)
            elif name == "run_facebook_rule_now":
                try:
                    rule_id = int(args.get("rule_id"))
                except Exception:
                    rule_id = 0
                if rule_id:
                    summary = f"سأشغّل المهمة رقم {rule_id} الآن. أوافق؟ / Run saved rule {rule_id} now?"
                    self.db.set_pending_action(session_id, "run_facebook_rule_now", {"rule_id": rule_id}, summary)
                    self._activity("agent_plan_preview", f"run_rule={rule_id}", status, "بانتظار موافقتك / Waiting for approval")
                    return AgentResponse(summary, used_tools=True, used_model=True)
            elif name == "prepare_facebook_campaign":
                instruction = str(args.get("instruction") or text).strip() or text
                try:
                    plan = SmartPlanner("ar").parse(
                        instruction,
                        default_source_page=self.settings.default_source_page,
                        default_interval=60,
                        default_max_groups=100,
                        default_no_repeat_days=14,
                    )
                    return self._preview_plan(plan, session_id, status=status, hammer_used=True)
                except SmartPlannerError as exc:
                    return AgentResponse(str(exc), used_tools=True, used_model=True)

        # Robust fallback for Arabic phrasing or model/tool-template mismatch.
        if _STATUS_RE.search(text):
            result = self.tools.execute("facebook_status")
            return AgentResponse(result.text, used_tools=True)
        if _DISCOVER_RE.search(text):
            summary = "سأفتح جلسة Facebook المحفوظة وأحدّث قائمة المجموعات. هل أوافق؟ / Refresh joined Facebook groups?"
            self.db.set_pending_action(session_id, "discover_facebook_groups", {}, summary)
            return AgentResponse(summary, used_tools=True)
        count_match = _COUNT_RE.search(text)
        if count_match:
            # Best-effort keyword: take the final Arabic/English token after group wording.
            keyword = ""
            m = re.search(r"(?:كلمة|اسمها|contains?|named?)\s+[«\"']?([^»\"'،,.!?]+)", text, re.I)
            if m:
                keyword = m.group(1).strip()
            count = self.db.count_groups(keyword)
            return AgentResponse(f"عدد المجموعات: {count}. / Groups: {count}.", used_tools=True)
        run_match = _RUN_RULE_RE.search(text)
        if run_match:
            rule_id = int(run_match.group(1))
            summary = f"سأشغّل المهمة رقم {rule_id} الآن. أوافق؟ / Run rule {rule_id} now?"
            self.db.set_pending_action(session_id, "run_facebook_rule_now", {"rule_id": rule_id}, summary)
            return AgentResponse(summary, used_tools=True)
        if _ACTION_RE.search(text):
            planner = SmartPlanner("ar")
            try:
                plan = planner.parse(
                    text,
                    default_source_page=self.settings.default_source_page,
                    default_interval=60,
                    default_max_groups=100,
                    default_no_repeat_days=14,
                )
                return self._preview_plan(plan, session_id, status=status)
            except SmartPlannerError as exc:
                return AgentResponse(str(exc), used_tools=True)

        # Last fallback: ordinary Hammer chat using the same single model.
        reply = self.chat_engine.reply(HAMMER, history, text, max_tokens, timeout, status=status)
        return AgentResponse(reply.text, used_model=reply.used_model)

    def _preview_plan(self, plan: SmartPlan, session_id: int, edited: bool = False, status=None, hammer_used: bool = False) -> AgentResponse:
        keyword = plan.group_keyword or ""
        matching = self.db.list_groups(keyword=keyword, limit=500)
        count = len(matching)
        examples = "، ".join(g["name"] for g in matching[:5])
        plan_dict = plan.to_dict()
        summary = plan.summary("ar")
        extra = f"\n\nالمجموعات المطابقة المحفوظة الآن: {count}. / Matching saved groups: {count}."
        if examples:
            extra += f"\nأمثلة / Examples: {examples}"
        if count == 0:
            extra += "\nإذا لم تُكتشف المجموعات بعد، افتح Status/Advanced أو قل: اكتشف مجموعات Facebook."
        question = "\n\nهل أعتمد هذه المهمة؟ اكتب «نعم» أو عدّلها بكلام طبيعي. / Approve, cancel, or edit naturally."
        prefix = "عدّلت الخطة / Updated plan:\n" if edited else "فهمت طلبك. الخطة قبل التنفيذ / Plan before execution:\n"
        full = prefix + summary + extra + question
        self.db.set_pending_action(session_id, "save_facebook_share_rule", plan_dict, full)
        self._activity("agent_plan_preview", f"groups={count}; hammer={hammer_used}; {plan.name}", status, "الخطة جاهزة وتنتظر موافقتك / Plan ready")
        if not self.settings.confirm_external_actions:
            result = self.tools.execute("save_facebook_share_rule", plan_dict)
            self.db.clear_pending_action(session_id)
            return AgentResponse(result.text, used_tools=True, used_model=hammer_used)
        return AgentResponse(full, used_tools=True, used_model=hammer_used)
