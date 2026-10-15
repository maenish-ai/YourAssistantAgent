from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Any

from ..ai.engine import ChatEngine
from ..ai.profiles import AgentProfile
from ..config import Settings
from ..storage.db import ChatDB
from .facebook_service import FacebookService
from .legacy_smart import SmartPlan, SmartPlanner, SmartPlannerError
from .tools import SMOLAGENTS_AVAILABLE, ToolRegistry


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
_DISCOVER_RE = re.compile(r"(?:اكتشف|اكتشاف|تعرف|تعرّف|حدث|حدّث|refresh|discover).{0,30}(?:جروب|مجموع|groups?)", re.I)
_STATUS_RE = re.compile(r"(?:حالة|وضع|متصل|الاتصال|status|connected).{0,25}(?:فيسبوك|facebook)", re.I)


class SmartAgentController:
    """Conversation-first agent with an allow-listed tool layer.

    Normal conversation goes to the selected local chat model. Work instructions
    are converted into a preview, counted against the saved groups, and only then
    executed after confirmation. The tool contract uses Hugging Face smolagents
    when available, but we intentionally do NOT expose CodeAgent/arbitrary Python
    execution on the user's PC.
    """

    def __init__(self, db: ChatDB, settings: Settings, chat_engine: ChatEngine, facebook: FacebookService):
        self.db = db
        self.settings = settings
        self.chat_engine = chat_engine
        self.facebook = facebook
        self.tools = ToolRegistry(db, facebook)

    def update_settings(self, settings: Settings) -> None:
        self.settings = settings
        self.facebook.update_settings(settings)

    @property
    def framework_label(self) -> str:
        return "smolagents tools" if SMOLAGENTS_AVAILABLE else "built-in compatible tools"

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

        # Pending approvals survive restart and are scoped to one conversation.
        pending = self.db.get_pending_action(session_id)
        if pending:
            if _CANCEL_RE.match(normalized):
                self.db.clear_pending_action(session_id)
                self.db.add_activity("agent_action_cancelled", pending.get("summary", ""))
                return AgentResponse("تمام، ألغيت العملية المعلّقة.", used_tools=True)
            if _CONFIRM_RE.match(normalized):
                result = self.tools.execute(pending["tool_name"], pending.get("arguments") or {})
                self.db.clear_pending_action(session_id)
                self.db.add_activity("agent_action_executed" if result.ok else "agent_action_error", result.text)
                return AgentResponse(result.text, used_tools=True)

            # A natural follow-up such as "خليها الساعة 9" edits the preview.
            if pending.get("tool_name") == "save_facebook_share_rule":
                try:
                    context = pending.get("arguments") or {}
                    plan = SmartPlanner("ar" if profile.key == "arabic" else "en").parse(
                        text,
                        default_source_page=self.settings.default_source_page,
                        context_plan=context,
                    )
                    return self._preview_plan(plan, session_id, edited=True)
                except SmartPlannerError:
                    # Not an edit: keep the pending action, but answer the new
                    # message normally rather than losing the user's preview.
                    pass

        if not self.settings.smart_agent_enabled:
            reply = self.chat_engine.reply(profile, history, text, max_tokens, timeout, status=status)
            return AgentResponse(reply.text, used_model=reply.used_model)

        # Safe read-only/direct tool intents.
        if _STATUS_RE.search(text):
            result = self.tools.execute("facebook_status")
            return AgentResponse(result.text, used_tools=True)
        if _DISCOVER_RE.search(text):
            # Discovery opens the browser and is a real action, so stage it.
            summary = "سأفتح جلسة Facebook المحفوظة وأحدّث قائمة المجموعات المنضم إليها الحساب. أوافق؟"
            self.db.set_pending_action(session_id, "discover_facebook_groups", {}, summary)
            return AgentResponse(summary, used_tools=True)

        # Facebook campaign/work instruction. This parser accepts Arabic and
        # English, written/numeric times, natural group-filter wording, and
        # follow-up edits; it is not tied to specific place names.
        if _ACTION_RE.search(text):
            planner = SmartPlanner("ar" if profile.key == "arabic" else "en")
            try:
                plan = planner.parse(
                    text,
                    default_source_page=self.settings.default_source_page,
                    default_interval=60,
                    default_max_groups=100,
                    default_no_repeat_days=14,
                )
                return self._preview_plan(plan, session_id)
            except SmartPlannerError as exc:
                # If the instruction looks like work but needs one missing fact,
                # return the precise clarification instead of hallucinating.
                return AgentResponse(str(exc), used_tools=True)

        # Ordinary conversation remains a real chat. "كيف حالك؟" and other
        # common greetings return instantly from ChatEngine's fast path; richer
        # conversation uses the selected local model.
        reply = self.chat_engine.reply(profile, history, text, max_tokens, timeout, status=status)
        return AgentResponse(reply.text, used_model=reply.used_model)

    def _preview_plan(self, plan: SmartPlan, session_id: int, edited: bool = False) -> AgentResponse:
        keyword = plan.group_keyword or ""
        matching = self.db.list_groups(keyword=keyword, limit=500)
        count = len(matching)
        examples = "، ".join(g["name"] for g in matching[:5])
        plan_dict = plan.to_dict()
        summary = plan.summary("ar")
        extra = f"\n\nالمجموعات المطابقة المحفوظة الآن: {count}."
        if examples:
            extra += f"\nأمثلة: {examples}"
        if count == 0:
            extra += "\nإذا كانت المجموعات غير مكتشفة بعد، حدّثها من الإعدادات أو قل لي: اكتشف مجموعات Facebook."
        question = "\n\nهل أعتمد هذه المهمة؟ اكتب «نعم» للاعتماد أو عدّلها بكلام طبيعي مثل «خليها الساعة 9»."
        full = ("عدّلت الخطة:\n" if edited else "فهمت طلبك. هذه الخطة قبل التنفيذ:\n") + summary + extra + question
        self.db.set_pending_action(session_id, "save_facebook_share_rule", plan_dict, full)
        self.db.add_activity("agent_plan_preview", f"groups={count}; {plan.name}")
        if not self.settings.confirm_external_actions:
            result = self.tools.execute("save_facebook_share_rule", plan_dict)
            self.db.clear_pending_action(session_id)
            return AgentResponse(result.text, used_tools=True)
        return AgentResponse(full, used_tools=True)
