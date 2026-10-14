from __future__ import annotations

import json
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, Mapping

import requests

from .local_ai_runtime import (
    LocalAIRuntime, LocalAIRuntimeError, LOCAL_AI_MODEL_NAME,
    LOCAL_AI_PROFILE_AUTO, LOCAL_AI_PROFILE_ARABIC, LOCAL_AI_PROFILE_GENERAL,
)
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
    source: str = "parser"  # local_ai | external_ai | parser
    intent: str = "campaign"  # campaign | status | rules | github | help | conversation
    reply: str = ""


class AgentBrain:
    """Hybrid employee-style language brain.

    v1.2 is local-first with a Dual Local Brain running through llama.cpp:
    RightNow Arabic 0.5B for Arabic messages and Qwen3 0.6B for general text.
    Auto mode loads only one model at a time and can fall back to the alternate
    bundled model on a hard failure. An optional OpenAI-compatible endpoint can
    still be selected. Ambiguity that could broaden an audience or change a
    schedule is returned as a clarification question instead of a guess.
    """

    def __init__(self, db, security, language: str = "ar"):
        self.db = db
        self.security = security
        self.language = language if language in {"ar", "en"} else "ar"

    @property
    def enabled(self) -> bool:
        # New local AI is enabled by default, independently of the old v1.0 key toggle.
        return bool(self.db.get_setting("agent_ai_enabled", True))

    @property
    def provider(self) -> str:
        value = str(self.db.get_setting("agent_ai_provider", "local") or "local").strip().lower()
        return value if value in {"local", "external"} else "local"

    @property
    def local_profile(self) -> str:
        value = str(self.db.get_setting("local_ai_profile", LOCAL_AI_PROFILE_AUTO) or LOCAL_AI_PROFILE_AUTO).strip().lower()
        return value if value in {LOCAL_AI_PROFILE_AUTO, LOCAL_AI_PROFILE_GENERAL, LOCAL_AI_PROFILE_ARABIC} else LOCAL_AI_PROFILE_AUTO

    @property
    def model(self) -> str:
        if self.provider == "local":
            custom = str(self.db.get_setting("local_ai_model_path", "") or "").strip()
            return custom or LOCAL_AI_MODEL_NAME
        return str(self.db.get_setting("external_ai_model", "") or "").strip()

    @property
    def external_endpoint(self) -> str:
        value = str(self.db.get_setting("external_ai_endpoint", "") or "").strip()
        return value or "https://api.openai.com/v1/chat/completions"

    @property
    def external_api_key(self) -> str:
        # v1.0 stored an OpenAI-specific key. Keep it as a migration fallback.
        return str(
            self.security.get_secret("external_ai_api_key")
            or self.security.get_secret("openai_api_key")
            or ""
        ).strip()

    def local_runtime(self, text: str = "", profile_override: str = "") -> LocalAIRuntime:
        custom = str(self.db.get_setting("local_ai_model_path", "") or "").strip()
        if custom:
            return LocalAIRuntime(model_path=custom, profile=LOCAL_AI_PROFILE_GENERAL)
        profile = str(profile_override or "").strip().lower()
        if profile not in {LOCAL_AI_PROFILE_GENERAL, LOCAL_AI_PROFILE_ARABIC}:
            profile = LocalAIRuntime.choose_profile(self.local_profile, text=text, language_hint=self.language)
        return LocalAIRuntime(profile=profile)

    def is_configured(self) -> bool:
        if not self.enabled:
            return False
        custom = str(self.db.get_setting("local_ai_model_path", "") or "").strip()
        if custom:
            local_ready = self.local_runtime().available
        else:
            available = LocalAIRuntime.bundled_profiles_available()
            if self.local_profile == LOCAL_AI_PROFILE_AUTO:
                local_ready = any(available.values())
            else:
                local_ready = bool(available.get(self.local_profile))
        if self.provider == "external":
            return bool(self.external_endpoint and self.model and self.external_api_key) or local_ready
        return local_ready

    @staticmethod
    def _schema_example() -> dict[str, Any]:
        return {
            "intent": "campaign",
            "needs_clarification": False,
            "question": "",
            "reply": "",
            "understanding": "Short human-readable summary of what you understood",
            "confidence": 0.92,
            "plans": [
                {
                    "name": "",
                    "source_page_url": "",
                    "schedule_kind": "once",
                    "run_time": "20:00",
                    "run_once_at": "2026-10-14T20:00:00",
                    "weekdays": [],
                    "post_mode": "fixed",
                    "post_offset": 0,
                    "group_keyword": "خلدة",
                    "all_groups": False,
                    "max_groups": 100,
                    "interval_seconds": 60,
                    "no_repeat_days": 14,
                }
            ],
        }

    def _instructions(self) -> str:
        language = "Arabic/Jordanian dialect" if self.language == "ar" else "English"
        schema = json.dumps(self._schema_example(), ensure_ascii=False, indent=2)
        return f"""You are the language-understanding brain of a private Windows assistant used by one business owner.
You behave like a careful human employee. Understand natural {language}, mixed Arabic/English, casual speech,
voice-dictation errors, short follow-up edits, and context. Do NOT require exact trigger words.

You manage intents around Facebook campaign planning, status/rules questions, GitHub deployment help,
Telegram help, and normal short conversation. You never perform a risky action merely because the user mentioned it;
you return a structured interpretation so the desktop app can ask for confirmation.

CRITICAL RULES:
1) Meaning over keywords. Place names such as خلدة / ماحص / صويلح / الفحيص / دابوق are examples only.
   Any text can be a group-name filter. If the user says "الجروبات اللي إلها علاقة بخلدة" infer group_keyword="خلدة".
2) Never silently broaden a filtered request to all groups. all_groups=true ONLY when the user explicitly says all/every group.
3) If a required fact is truly ambiguous, set needs_clarification=true and ask ONE short natural question.
4) Follow-up edits like "لا خليها بكرة 9" modify CURRENT_CONTEXT instead of asking the user to repeat everything.
5) "today/اليوم" means one time today. "tomorrow/بكرة" means one time tomorrow. Recurring requires words like every/daily/كل يوم or named weekdays.
6) Latest post => post_offset=0, fixed. Previous post => 1. Rotation only if explicitly requested.
7) interval_seconds minimum is 30. If unspecified, use DEFAULT_INTERVAL_SECONDS.
8) The source page may come from DEFAULT_SOURCE or CURRENT_CONTEXT. Do not invent a Facebook URL.
9) Admin approval: a share accepted by Facebook for admin review is a successful submission with Pending Approval, not a failure, and must not be resent.
10) If intent is status/rules/github/help/conversation, plans may be empty and reply should answer naturally. Do not turn every sentence into a campaign.
11) Return JSON ONLY. No markdown, no analysis, no <think> tags.

Valid intent values: campaign, status, rules, github, telegram, help, conversation.
Valid schedule_kind: once, recurring.
Valid post_mode: fixed, rotation.
run_once_at must be local ISO datetime when schedule_kind=once.
weekdays use Monday=0 ... Sunday=6. Empty weekdays with recurring means every day.

Return exactly this object shape (values are examples, not defaults):
{schema}
"""

    @staticmethod
    def _extract_json_from_text(text: str) -> dict[str, Any]:
        return LocalAIRuntime.extract_json_object(text)

    def _external_chat_json(self, system_prompt: str, user_prompt: str) -> dict[str, Any]:
        body = {
            "model": self.model,
            "messages": [
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt},
            ],
            "temperature": 0.15,
            "max_tokens": 1400,
            "stream": False,
        }
        headers = {"Content-Type": "application/json"}
        if self.external_api_key:
            headers["Authorization"] = f"Bearer {self.external_api_key}"
        try:
            resp = requests.post(self.external_endpoint, headers=headers, json=body, timeout=60)
            resp.raise_for_status()
            payload = resp.json()
            content = payload["choices"][0]["message"]["content"]
            return self._extract_json_from_text(content)
        except Exception as exc:
            raise AgentBrainError(f"External AI connection failed: {exc}") from exc

    def _payload_to_interpretation(
        self,
        payload: Mapping[str, Any],
        command: str,
        default_source_page: str,
        default_interval: int,
        default_max_groups: int,
        default_no_repeat_days: int,
        source_name: str = "ai",
    ) -> BrainInterpretation:
        intent = str(payload.get("intent") or "campaign").strip().lower()
        if intent not in {"campaign", "status", "rules", "github", "telegram", "help", "conversation"}:
            intent = "campaign"
        needs = bool(payload.get("needs_clarification", False))
        question = str(payload.get("question") or "").strip()
        reply = str(payload.get("reply") or "").strip()
        understanding = str(payload.get("understanding") or "").strip()
        try:
            confidence = max(0.0, min(1.0, float(payload.get("confidence", 0.0))))
        except Exception:
            confidence = 0.0
        if needs:
            return BrainInterpretation([], True, question, understanding, confidence, source_name, intent, reply)

        if intent != "campaign":
            return BrainInterpretation([], False, "", understanding, confidence, source_name, intent, reply or understanding)

        plans: list[SmartPlan] = []
        for raw in payload.get("plans") or []:
            if not isinstance(raw, Mapping):
                continue
            all_groups = bool(raw.get("all_groups", False))
            keyword = "" if all_groups else SmartPlanner._clean_keyword(str(raw.get("group_keyword") or ""))
            if not all_groups and not keyword:
                raise AgentBrainError(
                    "فهمت أنك تريد فلترة الجروبات، لكن لم أحدد اسم/شرط المجموعة بثقة. لن أحولها إلى كل الجروبات."
                    if self.language == "ar" else
                    "I understood that group filtering is required, but I could not identify the filter safely. I will not broaden it to all groups."
                )

            source = str(raw.get("source_page_url") or default_source_page or "").strip()
            if not source:
                raise AgentBrainError("حدد صفحة المصدر أولًا." if self.language == "ar" else "Set the source page first.")

            run_time = str(raw.get("run_time") or "20:00").strip()
            try:
                hh, mm = [int(x) for x in run_time.split(":", 1)]
                if not (0 <= hh <= 23 and 0 <= mm <= 59):
                    raise ValueError
                run_time = f"{hh:02d}:{mm:02d}"
            except Exception:
                raise AgentBrainError("الوقت الذي فهمه الوكيل غير صالح." if self.language == "ar" else "The interpreted time is invalid.")

            schedule_kind = str(raw.get("schedule_kind") or "recurring").strip().lower()
            run_once_at = str(raw.get("run_once_at") or "").strip() if schedule_kind == "once" else ""
            weekdays = []
            for x in raw.get("weekdays") or []:
                try:
                    n = int(x)
                except Exception:
                    continue
                if 0 <= n <= 6:
                    weekdays.append(n)
            weekdays = sorted(set(weekdays))

            if schedule_kind == "once":
                if not run_once_at:
                    raise AgentBrainError("الموعد لم يُفهم بشكل كامل. حدده مرة ثانية." if self.language == "ar" else "The one-time schedule is incomplete.")
                try:
                    when = datetime.fromisoformat(run_once_at)
                    if when <= datetime.now():
                        raise AgentBrainError("الموعد الذي فهمه الوكيل مضى بالفعل." if self.language == "ar" else "The interpreted schedule is already in the past.")
                except ValueError as exc:
                    raise AgentBrainError("صيغة الموعد غير صحيحة." if self.language == "ar" else "The interpreted datetime is invalid.") from exc

            try:
                max_groups = int(raw.get("max_groups") or default_max_groups)
            except Exception:
                max_groups = default_max_groups
            try:
                interval = int(raw.get("interval_seconds") or default_interval)
            except Exception:
                interval = default_interval
            try:
                no_repeat = int(raw.get("no_repeat_days") if raw.get("no_repeat_days") is not None else default_no_repeat_days)
            except Exception:
                no_repeat = default_no_repeat_days

            plan = SmartPlan(
                name=str(raw.get("name") or "").strip() or (f"ذكي - {keyword or 'كل الجروبات'}" if self.language == "ar" else f"Smart - {keyword or 'All groups'}"),
                command_text=command,
                source_page_url=source,
                weekdays=weekdays,
                run_time=run_time,
                run_once_at=run_once_at,
                post_mode="rotation" if str(raw.get("post_mode") or "").lower() == "rotation" else "fixed",
                post_offset=max(0, int(raw.get("post_offset") or 0)),
                group_keyword=keyword,
                max_groups=max(1, min(max_groups, 500)),
                interval_seconds=max(30, min(interval, 21600)),
                no_repeat_days=max(0, min(no_repeat, 3650)),
                share_mode="native_share",
            )
            plans.append(plan)

        if not plans:
            raise AgentBrainError("لم أستطع تكوين خطة تنفيذ آمنة من كلامك." if self.language == "ar" else "I could not build a safe execution plan from that instruction.")
        return BrainInterpretation(plans, False, "", understanding, confidence, source_name, intent, reply)

    def _build_user_text(
        self,
        command: str,
        default_source_page: str,
        default_interval: int,
        default_max_groups: int,
        default_no_repeat_days: int,
        context_plan: SmartPlan | Mapping[str, Any] | None,
        conversation_context: str,
    ) -> str:
        context = SmartPlanner._coerce_context(context_plan)
        now = datetime.now().replace(microsecond=0).isoformat()
        context_json = json.dumps(context.to_dict() if context else {}, ensure_ascii=False)
        owner_name = str(self.db.get_setting("owner_name", "") or "").strip()
        business_name = str(self.db.get_setting("business_name", "") or "").strip()
        try:
            group_rows = self.db.list_groups(enabled_only=True, limit=80)
            group_names = [str(r["name"]) for r in group_rows]
        except Exception:
            group_names = []
        return (
            f"CURRENT_LOCAL_DATETIME: {now}\n"
            f"OWNER_NAME: {owner_name}\n"
            f"BUSINESS_NAME: {business_name}\n"
            f"KNOWN_FACEBOOK_GROUP_NAMES: {json.dumps(group_names, ensure_ascii=False)}\n"
            f"DEFAULT_SOURCE: {default_source_page}\n"
            f"DEFAULT_INTERVAL_SECONDS: {int(default_interval)}\n"
            f"DEFAULT_MAX_GROUPS: {int(default_max_groups)}\n"
            f"DEFAULT_NO_REPEAT_DAYS: {int(default_no_repeat_days)}\n"
            f"CURRENT_CONTEXT: {context_json}\n"
            f"RECENT_CONVERSATION: {conversation_context[-8000:]}\n"
            f"USER_MESSAGE: {command}"
        )

    def interpret_local(
        self,
        command: str,
        default_source_page: str = "",
        default_interval: int = 60,
        default_max_groups: int = 100,
        default_no_repeat_days: int = 14,
        context_plan: SmartPlan | Mapping[str, Any] | None = None,
        conversation_context: str = "",
        profile_override: str = "",
    ) -> BrainInterpretation:
        runtime = self.local_runtime(command, profile_override=profile_override)
        user_text = self._build_user_text(
            command, default_source_page, default_interval, default_max_groups,
            default_no_repeat_days, context_plan, conversation_context,
        )
        try:
            payload = runtime.chat_json(self._instructions(), user_text)
        except LocalAIRuntimeError as exc:
            raise AgentBrainError(str(exc)) from exc
        return self._payload_to_interpretation(
            payload, command, default_source_page, default_interval,
            default_max_groups, default_no_repeat_days, "local_ai"
        )

    def interpret_external(
        self,
        command: str,
        default_source_page: str = "",
        default_interval: int = 60,
        default_max_groups: int = 100,
        default_no_repeat_days: int = 14,
        context_plan: SmartPlan | Mapping[str, Any] | None = None,
        conversation_context: str = "",
    ) -> BrainInterpretation:
        user_text = self._build_user_text(
            command, default_source_page, default_interval, default_max_groups,
            default_no_repeat_days, context_plan, conversation_context,
        )
        payload = self._external_chat_json(self._instructions(), user_text)
        return self._payload_to_interpretation(
            payload, command, default_source_page, default_interval,
            default_max_groups, default_no_repeat_days, "external_ai"
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
        errors: list[str] = []
        if self.enabled:
            if self.provider == "external" and self.external_api_key and self.model:
                try:
                    return self.interpret_external(
                        command, default_source_page, default_interval, default_max_groups,
                        default_no_repeat_days, context_plan, conversation_context,
                    )
                except AgentBrainError as exc:
                    errors.append(str(exc))
            # Local AI is always the free fallback when its bundled files exist.
            selected_runtime = self.local_runtime(command)
            if selected_runtime.available:
                try:
                    return self.interpret_local(
                        command, default_source_page, default_interval, default_max_groups,
                        default_no_repeat_days, context_plan, conversation_context,
                    )
                except AgentBrainError as exc:
                    errors.append(str(exc))
                    # Auto mode gets one hard-failure fallback to the other bundled
                    # local model. Only one model remains loaded at a time.
                    if self.local_profile == LOCAL_AI_PROFILE_AUTO:
                        alternate = (
                            LOCAL_AI_PROFILE_GENERAL
                            if selected_runtime.profile == LOCAL_AI_PROFILE_ARABIC
                            else LOCAL_AI_PROFILE_ARABIC
                        )
                        alternate_runtime = self.local_runtime(command, profile_override=alternate)
                        if alternate_runtime.available:
                            try:
                                return self.interpret_local(
                                    command, default_source_page, default_interval, default_max_groups,
                                    default_no_repeat_days, context_plan, conversation_context,
                                    profile_override=alternate,
                                )
                            except AgentBrainError as fallback_exc:
                                errors.append(str(fallback_exc))

        planner = SmartPlanner(self.language)
        fallback_context = context_plan if planner.is_followup(command) else None
        try:
            plans = planner.parse_many(
                command,
                default_source_page=default_source_page,
                default_interval=default_interval,
                default_max_groups=default_max_groups,
                default_no_repeat_days=default_no_repeat_days,
                context_plan=fallback_context,
            )
        except SmartPlannerError:
            if errors:
                raise AgentBrainError(errors[-1])
            raise
        note = ""
        if errors:
            note = (
                "تعذر تشغيل العقل الذكي، فتم استخدام الفهم المحلي الاحتياطي."
                if self.language == "ar" else
                "The AI brain was unavailable, so the deterministic fallback parser was used."
            )
        return BrainInterpretation(plans, False, "", note, 0.58 if plans else 0.0, "parser", "campaign", "")

    def test_connection(self) -> tuple[bool, str]:
        if not self.enabled:
            return False, "AI Brain is disabled"
        if self.provider == "external":
            if not (self.model and self.external_api_key):
                # Still report the bundled local engine if it is available.
                ok, msg = self.local_runtime("مرحبا" if self.language == "ar" else "hello").test()
                return ok, ("External AI is not configured; " + msg) if ok else msg
            try:
                data = self._external_chat_json(
                    "Return JSON only.",
                    'Return exactly {"ok":true,"message":"ready"}',
                )
                if bool(data.get("ok")):
                    return True, "External AI connected"
                return False, f"Unexpected external AI response: {data}"
            except Exception as exc:
                ok, msg = self.local_runtime("مرحبا" if self.language == "ar" else "hello").test()
                if ok:
                    return True, f"External AI failed, but free Local AI is ready — {msg}"
                return False, str(exc)
        return self.local_runtime("مرحبا" if self.language == "ar" else "hello").test()
