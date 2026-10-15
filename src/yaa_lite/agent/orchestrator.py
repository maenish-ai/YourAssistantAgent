from __future__ import annotations

import re
from dataclasses import dataclass
from typing import TYPE_CHECKING

from ..ai.engine import ChatEngine
from ..ai.profiles import AgentProfile, HAMMER
from ..config import Settings
from ..storage.db import ChatDB
from .facebook_service import FacebookService
from .hammer_agent import HAMMER_MODEL_LABEL, HammerAgentRouter
from .legacy_smart import SmartPlan, SmartPlanner, SmartPlannerError
from .tools import ToolRegistry

if TYPE_CHECKING:
    from ..backup.service import BackupService


@dataclass
class AgentResponse:
    text: str
    used_model: bool = False
    used_tools: bool = False
    detail: str = ""


_CONFIRM_RE = re.compile(r"^(?:نعم|اه|آه|اوافق|أوافق|وافق|موافق|تمام|نفذ|نفّذ|اعتمد|yes|ok|okay|confirm|approve)$", re.I)
_CANCEL_RE = re.compile(r"^(?:لا|الغ|ألغي|الغاء|إلغاء|بلاش|cancel|no|stop)$", re.I)


class SmartAgentController:
    """Hammer-first controller.

    v2.0 deliberately removes keyword/quick-chat routing. Apart from deterministic
    confirmation/cancel safety handling, every user utterance is sent to Hammer.
    The app is the UI, state store and permission boundary; Hammer is the only
    conversational/reasoning model.
    """

    def __init__(self, db: ChatDB, settings: Settings, chat_engine: ChatEngine,
                 facebook: FacebookService, backup: BackupService | None = None):
        self.db = db
        self.settings = settings
        self.chat_engine = chat_engine
        self.facebook = facebook
        self.backup = backup
        self.tools = ToolRegistry(db, facebook, backup)
        self.hammer = HammerAgentRouter(chat_engine.runtime)

    def t(self, ar: str, en: str) -> str:
        return ar if self.settings.interface_language == "ar" else en

    def update_settings(self, settings: Settings) -> None:
        self.settings = settings
        self.facebook.update_settings(settings)
        if self.backup is not None:
            self.backup.update_settings(settings)

    @property
    def framework_label(self) -> str:
        return f"{HAMMER_MODEL_LABEL} — primary local agent"

    def _activity(self, kind: str, detail: str, status=None, friendly: str | None = None) -> None:
        self.db.add_activity(kind, detail)
        if status and friendly:
            status(friendly)

    def _preference_context(self) -> dict:
        language = self.settings.reply_language
        dialect = self.settings.arabic_dialect
        style = self.settings.personality_style
        custom = (self.settings.personality_prompt or "").strip()
        text = (
            f"User preferences for this app session: reply_language={language}; arabic_dialect={dialect}; "
            f"assistant_name={self.settings.assistant_name}; personality={style}. "
            + (f"Custom personality instruction: {custom}" if custom else "")
        )
        return {"role": "system", "content": text}

    def _hammer_plain_reply(self, history: list[dict], prompt: str, max_tokens: int, timeout: int, status=None) -> str:
        result = self.chat_engine.reply(HAMMER, [self._preference_context()] + history, prompt, max_tokens, timeout, status=status)
        return result.text

    def handle(self, profile: AgentProfile, history: list[dict], user_text: str, session_id: int,
               max_tokens: int, timeout: int, status=None) -> AgentResponse:
        text = (user_text or "").strip()
        if not text:
            return AgentResponse("")

        pending = self.db.get_pending_action(session_id)
        if pending and _CANCEL_RE.match(" ".join(text.split())):
            self.db.clear_pending_action(session_id)
            self._activity("agent_action_cancelled", pending.get("summary", ""), status,
                           self.t("تم إلغاء العملية", "Action cancelled"))
            return AgentResponse(self.t("تمام، ألغيت العملية المعلّقة.", "Cancelled the pending action."), used_tools=True)

        if pending and _CONFIRM_RE.match(" ".join(text.split())):
            self._activity("agent_action_confirmed", pending.get("tool_name", ""), status,
                           self.t("تمت الموافقة — جاري التنفيذ", "Approved — executing"))
            result = self.tools.execute(pending["tool_name"], pending.get("arguments") or {})
            self.db.clear_pending_action(session_id)
            self._activity("agent_action_executed" if result.ok else "agent_action_error", result.text)
            # Safety gate is deterministic; Hammer then phrases the final result naturally.
            try:
                natural = self._hammer_plain_reply(
                    history,
                    self.t(
                        f"المستخدم وافق على الإجراء. هذه نتيجة أداة البرنامج: {result.text}\nاشرح النتيجة باختصار وبدون ادعاء أي شيء إضافي.",
                        f"The user approved the action. Application tool result: {result.text}\nExplain the result briefly without claiming anything else happened.",
                    ),
                    max_tokens, timeout, status,
                )
                return AgentResponse(natural, used_model=True, used_tools=True, detail=result.text)
            except Exception:
                return AgentResponse(result.text, used_tools=True, detail=result.text)

        # If a plan is waiting and the user edits it naturally, tell Hammer about
        # the pending context. Hammer still decides what to do with the new text.
        hammer_history = [self._preference_context()] + list(history)
        if pending:
            hammer_history.append({
                "role": "assistant",
                "content": self.t(
                    "هناك خطة معلقة بانتظار الموافقة أو التعديل:\n" + str(pending.get("summary") or ""),
                    "There is a pending plan waiting for approval or edit:\n" + str(pending.get("summary") or ""),
                ),
            })

        self._activity("hammer_analyzing", text[:500], status,
                       self.t("Hammer يحلل الطلب", "Hammer is analyzing"))
        decision = self.hammer.decide(hammer_history, text, max_tokens=max_tokens, timeout=timeout, status=status)
        self._activity("hammer_decision", f"tool={decision.name}; args={decision.arguments}")

        name, args = decision.name, decision.arguments or {}
        if name == "respond":
            message = str(args.get("message") or decision.content or "").strip()
            if not message:
                message = self._hammer_plain_reply(history, text, max_tokens, timeout, status)
            return AgentResponse(message, used_model=True)

        if name in {"app_status", "facebook_status", "count_facebook_groups", "list_tasks", "backup_status"}:
            result = self.tools.execute(name, args)
            self._activity("hammer_tool_result", f"{name}: {result.text}", status,
                           self.t("تمت قراءة الحالة", "Status read"))
            try:
                natural = self._hammer_plain_reply(
                    history,
                    self.t(
                        f"سأل المستخدم: {text}\nاخترت أداة {name}، وكانت النتيجة:\n{result.text}\nجاوب المستخدم بشكل طبيعي ومختصر وبنفس لغته.",
                        f"User asked: {text}\nYou selected {name}; tool result:\n{result.text}\nAnswer naturally and concisely in the user's language.",
                    ),
                    max_tokens, timeout, status,
                )
                return AgentResponse(natural, used_model=True, used_tools=True, detail=result.text)
            except Exception:
                return AgentResponse(result.text, used_tools=True, detail=result.text)

        if name == "discover_facebook_groups":
            summary = self.t(
                "سأستخدم اتصال Facebook لتحديث قائمة المجموعات المنضم إليها الحساب. هذا إجراء خارجي. هل تريد التنفيذ؟",
                "I will use the Facebook connection to refresh joined groups. This is an external action. Approve?",
            )
            self.db.set_pending_action(session_id, "discover_facebook_groups", {}, summary)
            self._activity("agent_plan_preview", "discover_facebook_groups", status,
                           self.t("بانتظار موافقتك", "Waiting for approval"))
            return AgentResponse(summary, used_model=True, used_tools=True, detail="discover_facebook_groups")

        if name == "run_facebook_rule_now":
            try:
                rule_id = int(args.get("rule_id"))
            except Exception:
                rule_id = 0
            if not rule_id:
                return AgentResponse(self.t("لم يحدد Hammer رقم مهمة صالحًا.", "Hammer did not identify a valid task ID."), used_model=True)
            summary = self.t(f"سأشغّل المهمة رقم {rule_id} الآن. هل تريد التنفيذ؟",
                             f"I will run task #{rule_id} now. Approve?")
            self.db.set_pending_action(session_id, "run_facebook_rule_now", {"rule_id": rule_id}, summary)
            self._activity("agent_plan_preview", f"run_rule={rule_id}", status,
                           self.t("بانتظار موافقتك", "Waiting for approval"))
            return AgentResponse(summary, used_model=True, used_tools=True, detail=f"rule={rule_id}")

        if name == "prepare_facebook_campaign":
            instruction = str(args.get("instruction") or text).strip() or text
            context = pending.get("arguments") if pending and pending.get("tool_name") == "save_facebook_share_rule" else None
            try:
                plan = SmartPlanner("ar" if self.settings.interface_language == "ar" else "en").parse(
                    instruction,
                    default_source_page=self.settings.default_source_page,
                    default_interval=max(30, self.settings.facebook_interval_min_seconds),
                    default_max_groups=self.settings.confirmation_group_threshold if self.settings.confirmation_group_threshold > 0 else 100,
                    default_no_repeat_days=self.settings.facebook_no_repeat_days,
                    context_plan=context,
                )
                return self._preview_plan(plan, session_id, edited=bool(context), status=status)
            except SmartPlannerError as exc:
                # The plan parser is an application tool; Hammer stays the language layer.
                try:
                    msg = self._hammer_plain_reply(
                        history,
                        self.t(
                            f"أردت إنشاء مهمة Facebook لكن أداة التخطيط قالت: {exc}. اطلب من المستخدم المعلومة الناقصة فقط.",
                            f"You tried to create a Facebook task but the planner returned: {exc}. Ask only for the missing information.",
                        ), max_tokens, timeout, status,
                    )
                    return AgentResponse(msg, used_model=True, used_tools=True, detail=str(exc))
                except Exception:
                    return AgentResponse(str(exc), used_tools=True)

        # Unknown tool names are never executed. Hammer gets a final plain-chat
        # chance so the user still receives a useful response.
        self._activity("hammer_unknown_tool", name)
        fallback = self._hammer_plain_reply(
            history,
            self.t(
                f"رد على رسالة المستخدم بشكل طبيعي. لا تستخدم أدوات الآن. الرسالة: {text}",
                f"Reply naturally to the user. Do not use tools now. Message: {text}",
            ), max_tokens, timeout, status,
        )
        return AgentResponse(fallback, used_model=True)

    def _preview_plan(self, plan: SmartPlan, session_id: int, edited: bool = False, status=None) -> AgentResponse:
        keyword = plan.group_keyword or ""
        matching = self.db.list_groups(keyword=keyword, limit=500)
        count = len(matching)
        examples = "، ".join(g["name"] for g in matching[:5])
        plan_dict = plan.to_dict()
        summary = plan.summary("ar" if self.settings.interface_language == "ar" else "en")
        if self.settings.interface_language == "ar":
            prefix = "الخطة المعدلة:\n" if edited else "الخطة قبل التنفيذ:\n"
            extra = f"\n\nالمجموعات المطابقة المحفوظة الآن: {count}."
            if examples:
                extra += f"\nأمثلة: {examples}"
            question = "\n\nهل تريد اعتماد هذه المهمة؟ اكتب نعم، أو عدّلها بكلام طبيعي، أو ألغِها."
        else:
            prefix = "Updated plan:\n" if edited else "Plan before execution:\n"
            extra = f"\n\nMatching saved groups: {count}."
            if examples:
                extra += f"\nExamples: {examples}"
            question = "\n\nApprove this task? Say yes, edit it naturally, or cancel."
        full = prefix + summary + extra + question
        self.db.set_pending_action(session_id, "save_facebook_share_rule", plan_dict, full)
        self._activity("agent_plan_preview", f"groups={count}; {plan.name}", status,
                       self.t("الخطة جاهزة وتنتظر موافقتك", "Plan ready and waiting for approval"))
        if not self.settings.confirm_external_actions or self.settings.confirmation_policy == "auto":
            result = self.tools.execute("save_facebook_share_rule", plan_dict)
            self.db.clear_pending_action(session_id)
            return AgentResponse(result.text, used_tools=True, used_model=True, detail=result.text)
        return AgentResponse(full, used_tools=True, used_model=True, detail=summary)
