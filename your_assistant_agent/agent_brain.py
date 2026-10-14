from __future__ import annotations

import json
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, Mapping

import requests

from .smart_agent import SmartPlan, SmartPlanner, SmartPlannerError


class AgentBrainError(RuntimeError):
    pass


@dataclass
class BrainInterpretation:
    plans: list[SmartPlan] = field(default_factory=list)
    needs_clarification: bool = False
    question: str = ""
    understanding: str = ""
    confidence: float = 0.0
    source: str = "parser"  # ai | parser


class AgentBrain:
    """Hybrid campaign interpreter.

    The deterministic SmartPlanner remains the safe offline fallback. When the
    user has enabled the AI Brain and stored an OpenAI API key, natural-language
    instructions are interpreted by the Responses API first and converted into
    the exact same SmartPlan structure used by the scheduler.

    Safety rule: ambiguity that could broaden the audience, change the schedule,
    or pick the wrong post becomes a clarification question instead of an
    automatic guess.
    """

    API_URL = "https://api.openai.com/v1/responses"

    def __init__(self, db, security, language: str = "ar"):
        self.db = db
        self.security = security
        self.language = language if language in {"ar", "en"} else "ar"

    @property
    def enabled(self) -> bool:
        return bool(self.db.get_setting("smart_ai_enabled", False))

    @property
    def model(self) -> str:
        return str(self.db.get_setting("smart_ai_model", "gpt-6-luna") or "gpt-6-luna").strip()

    @property
    def api_key(self) -> str:
        return str(self.security.get_secret("openai_api_key") or "").strip()

    def is_configured(self) -> bool:
        return self.enabled and bool(self.api_key)

    @staticmethod
    def _schema() -> dict[str, Any]:
        plan = {
            "type": "object",
            "additionalProperties": False,
            "properties": {
                "name": {"type": "string"},
                "source_page_url": {"type": "string"},
                "schedule_kind": {"type": "string", "enum": ["once", "recurring"]},
                "run_time": {"type": "string"},
                "run_once_at": {"type": "string"},
                "weekdays": {"type": "array", "items": {"type": "integer"}},
                "post_mode": {"type": "string", "enum": ["fixed", "rotation"]},
                "post_offset": {"type": "integer"},
                "group_keyword": {"type": "string"},
                "all_groups": {"type": "boolean"},
                "max_groups": {"type": "integer"},
                "interval_seconds": {"type": "integer"},
                "no_repeat_days": {"type": "integer"},
            },
            "required": [
                "name", "source_page_url", "schedule_kind", "run_time", "run_once_at", "weekdays",
                "post_mode", "post_offset", "group_keyword", "all_groups", "max_groups",
                "interval_seconds", "no_repeat_days"
            ],
        }
        return {
            "type": "object",
            "additionalProperties": False,
            "properties": {
                "needs_clarification": {"type": "boolean"},
                "question": {"type": "string"},
                "understanding": {"type": "string"},
                "confidence": {"type": "number"},
                "plans": {"type": "array", "items": plan},
            },
            "required": ["needs_clarification", "question", "understanding", "confidence", "plans"],
        }

    def _instructions(self) -> str:
        return """You are the language-understanding brain of a Windows marketing automation agent.
Interpret the user's Arabic (especially Jordanian/Levantine colloquial Arabic), English, mixed Arabic/English,
voice-dictation mistakes, and natural follow-up edits like a careful human employee.

Your output is ONLY the structured object requested by the schema.

Rules:
1. Understand intent and meaning, not exact keywords. Examples such as خلدة، ماحص، صويلح، الفحيص، دابوق are arbitrary group-name filters; never hard-code a list of places.
2. If the user says groups whose name has/contains/includes X, put X in group_keyword and all_groups=false.
3. Use all_groups=true ONLY when the user clearly asks for all groups. Never broaden a filtered request to all groups.
4. If the audience/filter, post choice, or execution time is genuinely ambiguous, set needs_clarification=true and ask one short specific question. Do not guess.
5. The source Facebook page URL can come from DEFAULT_SOURCE when the user names the page but does not paste its URL.
6. latest/آخر منشور => post_offset=0; previous/السابق => 1; before previous => 2. Rotation => post_mode=rotation.
7. Today/اليوم is a one-time schedule. Tomorrow/غدًا/بكرة is a one-time schedule. Recurring weekday wording is recurring.
8. Weekdays use Monday=0 ... Sunday=6. An empty weekdays array for recurring means every day.
9. run_time must be HH:MM 24-hour local time. run_once_at must be local ISO datetime without timezone offset when schedule_kind=once, otherwise an empty string.
10. Inherit omitted details from CURRENT_CONTEXT for follow-up edits. RECENT_CONVERSATION may contain an earlier instruction and your clarification question; use the user's new answer to complete that unfinished request. Do not inherit a target from context if the user explicitly replaces it.
11. Respect defaults for interval/max/no-repeat when the user does not specify them.
12. Admin approval is not a failure state; the execution engine handles it separately. Do not alter the target because a group may require admin approval.
13. Be conservative. A wrong broad action is worse than asking a clarification question.
"""

    @staticmethod
    def _extract_output_text(payload: Mapping[str, Any]) -> str:
        direct = payload.get("output_text")
        if isinstance(direct, str) and direct.strip():
            return direct.strip()
        for item in payload.get("output") or []:
            if not isinstance(item, Mapping):
                continue
            for content in item.get("content") or []:
                if not isinstance(content, Mapping):
                    continue
                if content.get("type") in {"output_text", "text"}:
                    text = content.get("text")
                    if isinstance(text, str) and text.strip():
                        return text.strip()
        return ""

    def _payload_to_interpretation(
        self,
        payload: Mapping[str, Any],
        command: str,
        default_source_page: str,
        default_interval: int,
        default_max_groups: int,
        default_no_repeat_days: int,
    ) -> BrainInterpretation:
        needs = bool(payload.get("needs_clarification", False))
        question = str(payload.get("question") or "").strip()
        understanding = str(payload.get("understanding") or "").strip()
        try:
            confidence = max(0.0, min(1.0, float(payload.get("confidence", 0.0))))
        except Exception:
            confidence = 0.0
        if needs:
            return BrainInterpretation([], True, question, understanding, confidence, "ai")

        plans: list[SmartPlan] = []
        for raw in payload.get("plans") or []:
            if not isinstance(raw, Mapping):
                continue
            all_groups = bool(raw.get("all_groups", False))
            keyword = "" if all_groups else SmartPlanner._clean_keyword(str(raw.get("group_keyword") or ""))
            if not all_groups and not keyword:
                raise AgentBrainError(
                    "الذكاء فهم أن هناك فلترة للجروبات لكنه لم يحدد الكلمة. لن أنفذ على كل الجروبات."
                    if self.language == "ar" else
                    "The AI understood that group filtering is required but did not identify the filter. It will not broaden to all groups."
                )
            source = str(raw.get("source_page_url") or default_source_page or "").strip()
            if not source:
                raise AgentBrainError("حدد صفحة المصدر أولًا." if self.language == "ar" else "Set the source page first.")
            run_time = str(raw.get("run_time") or "20:00").strip()
            if not SmartPlanner._has_explicit_time("at " + run_time):
                run_time = "20:00"
            schedule_kind = str(raw.get("schedule_kind") or "recurring")
            run_once_at = str(raw.get("run_once_at") or "").strip() if schedule_kind == "once" else ""
            weekdays = [int(x) for x in (raw.get("weekdays") or []) if isinstance(x, int) and 0 <= int(x) <= 6]
            if schedule_kind == "once" and not run_once_at:
                raise AgentBrainError("لم يتم تحديد موعد المرة الواحدة بشكل واضح." if self.language == "ar" else "The one-time schedule is missing an exact datetime.")
            if schedule_kind == "once":
                try:
                    when = datetime.fromisoformat(run_once_at)
                    if when <= datetime.now():
                        raise AgentBrainError("الموعد الذي فهمه الوكيل مضى بالفعل." if self.language == "ar" else "The interpreted schedule is already in the past.")
                except ValueError as exc:
                    raise AgentBrainError("صيغة الموعد غير صحيحة." if self.language == "ar" else "The interpreted datetime is invalid.") from exc
            plan = SmartPlan(
                name=str(raw.get("name") or "").strip() or (f"ذكي - {keyword or 'كل الجروبات'}" if self.language == "ar" else f"Smart - {keyword or 'All groups'}"),
                command_text=command,
                source_page_url=source,
                weekdays=sorted(set(weekdays)),
                run_time=run_time,
                run_once_at=run_once_at,
                post_mode="rotation" if raw.get("post_mode") == "rotation" else "fixed",
                post_offset=max(0, int(raw.get("post_offset") or 0)),
                group_keyword=keyword,
                max_groups=max(1, min(int(raw.get("max_groups") or default_max_groups), 500)),
                interval_seconds=max(30, min(int(raw.get("interval_seconds") or default_interval), 21600)),
                no_repeat_days=max(0, min(int(raw.get("no_repeat_days") or default_no_repeat_days), 3650)),
                share_mode="native_share",
            )
            plans.append(plan)
        if not plans:
            raise AgentBrainError("لم أستطع تكوين خطة تنفيذ آمنة من الأمر." if self.language == "ar" else "I could not build a safe execution plan from the instruction.")
        return BrainInterpretation(plans, False, "", understanding, confidence, "ai")

    def interpret(
        self,
        command: str,
        default_source_page: str = "",
        default_interval: int = 60,
        default_max_groups: int = 100,
        default_no_repeat_days: int = 14,
        context_plan: SmartPlan | Mapping[str, Any] | None = None,
        conversation_context: str = "",
    ) -> BrainInterpretation:
        if not self.is_configured():
            raise AgentBrainError("AI Brain is not configured")
        context = SmartPlanner._coerce_context(context_plan)
        now = datetime.now().replace(microsecond=0).isoformat()
        context_json = json.dumps(context.to_dict() if context else {}, ensure_ascii=False)
        user_text = (
            f"CURRENT_LOCAL_DATETIME: {now}\n"
            f"DEFAULT_SOURCE: {default_source_page}\n"
            f"DEFAULT_INTERVAL_SECONDS: {int(default_interval)}\n"
            f"DEFAULT_MAX_GROUPS: {int(default_max_groups)}\n"
            f"DEFAULT_NO_REPEAT_DAYS: {int(default_no_repeat_days)}\n"
            f"CURRENT_CONTEXT: {context_json}\n"
            f"RECENT_CONVERSATION: {conversation_context[-6000:]}\n"
            f"USER_INSTRUCTION: {command}"
        )
        body = {
            "model": self.model,
            "instructions": self._instructions(),
            "input": user_text,
            "text": {
                "format": {
                    "type": "json_schema",
                    "name": "campaign_interpretation",
                    "strict": True,
                    "schema": self._schema(),
                }
            },
        }
        try:
            resp = requests.post(
                self.API_URL,
                headers={"Authorization": f"Bearer {self.api_key}", "Content-Type": "application/json"},
                json=body,
                timeout=30,
            )
        except requests.RequestException as exc:
            raise AgentBrainError(f"AI connection failed: {exc}") from exc
        if resp.status_code >= 400:
            try:
                detail = resp.json().get("error", {}).get("message") or resp.text
            except Exception:
                detail = resp.text
            raise AgentBrainError(f"AI API error {resp.status_code}: {str(detail)[:600]}")
        try:
            raw_response = resp.json()
            text = self._extract_output_text(raw_response)
            if not text:
                raise AgentBrainError("AI returned no structured text")
            parsed = json.loads(text)
        except AgentBrainError:
            raise
        except Exception as exc:
            raise AgentBrainError(f"Could not read AI response: {exc}") from exc
        return self._payload_to_interpretation(
            parsed,
            command,
            default_source_page,
            default_interval,
            default_max_groups,
            default_no_repeat_days,
        )

    def interpret_with_fallback(
        self,
        command: str,
        default_source_page: str = "",
        default_interval: int = 60,
        default_max_groups: int = 100,
        default_no_repeat_days: int = 14,
        context_plan: SmartPlan | Mapping[str, Any] | None = None,
        conversation_context: str = "",
    ) -> BrainInterpretation:
        ai_error = ""
        if self.is_configured():
            try:
                return self.interpret(
                    command,
                    default_source_page,
                    default_interval,
                    default_max_groups,
                    default_no_repeat_days,
                    context_plan,
                    conversation_context,
                )
            except AgentBrainError as exc:
                ai_error = str(exc)
        planner = SmartPlanner(self.language)
        try:
            plans = planner.parse_many(
                command,
                default_source_page=default_source_page,
                default_interval=default_interval,
                default_max_groups=default_max_groups,
                default_no_repeat_days=default_no_repeat_days,
                context_plan=context_plan,
            )
        except SmartPlannerError:
            if ai_error:
                raise AgentBrainError(ai_error)
            raise
        note = ""
        if ai_error:
            note = (
                "تعذر الوصول إلى AI Brain، فتم استخدام الفهم المحلي الآمن."
                if self.language == "ar" else
                "AI Brain was unavailable, so the safe local parser was used."
            )
        return BrainInterpretation(plans, False, "", note, 0.65 if plans else 0.0, "parser")

    def test_connection(self) -> tuple[bool, str]:
        if not self.enabled:
            return False, "AI Brain is disabled"
        if not self.api_key:
            return False, "API key is missing"
        body = {"model": self.model, "input": "Reply with exactly: OK"}
        try:
            resp = requests.post(
                self.API_URL,
                headers={"Authorization": f"Bearer {self.api_key}", "Content-Type": "application/json"},
                json=body,
                timeout=20,
            )
            if resp.status_code >= 400:
                return False, f"HTTP {resp.status_code}: {resp.text[:300]}"
            return True, "AI Brain connected"
        except Exception as exc:
            return False, str(exc)
