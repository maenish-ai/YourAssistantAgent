"""Your Assistant Agent v2.2 — direct personal-assistant architecture.

Qwen3 is the only reasoning/conversation brain. Normal conversation is returned
as normal assistant text. Application tools are exposed through Qwen's native
function-calling protocol; there is no synthetic `respond` tool in the primary
path.

The desktop application remains the permission boundary:
- safe/read-only tools may run automatically inside one assistant turn;
- publishing/running a Facebook campaign still requires deterministic approval;
- Facebook login/2FA/checkpoints remain manual and are never bypassed.

Legacy class/session names containing "hammer" are kept only for upgrade
compatibility with existing databases and imports.
"""
from __future__ import annotations

import json
from datetime import datetime
from typing import Any

FILTER_PREFIX = "__YAA_FILTER_V1__:"
_APPLIED = False


def _clean_list(value: Any, limit: int = 20) -> list[str]:
    if isinstance(value, str):
        value = [value]
    if not isinstance(value, list):
        return []
    out: list[str] = []
    for item in value:
        text = " ".join(str(item or "").split()).strip()
        if text and text not in out:
            out.append(text[:180])
        if len(out) >= limit:
            break
    return out


def encode_group_filter(
    include_keywords: Any = None,
    exclude_keywords: Any = None,
    exclude_names: Any = None,
    match_mode: str = "any",
) -> str:
    data = {
        "include_keywords": _clean_list(include_keywords),
        "exclude_keywords": _clean_list(exclude_keywords),
        "exclude_names": _clean_list(exclude_names),
        "match_mode": "all" if str(match_mode).lower() == "all" else "any",
    }
    return FILTER_PREFIX + json.dumps(data, ensure_ascii=False, separators=(",", ":"))


def decode_group_filter(value: str) -> dict | None:
    text = str(value or "")
    if not text.startswith(FILTER_PREFIX):
        return None
    try:
        data = json.loads(text[len(FILTER_PREFIX):])
    except Exception:
        return None
    if not isinstance(data, dict):
        return None
    return {
        "include_keywords": _clean_list(data.get("include_keywords")),
        "exclude_keywords": _clean_list(data.get("exclude_keywords")),
        "exclude_names": _clean_list(data.get("exclude_names")),
        "match_mode": "all" if str(data.get("match_mode")).lower() == "all" else "any",
    }


def _install_group_filtering() -> None:
    from .storage.db import ChatDB

    if getattr(ChatDB, "_yaa_v220_filter_patched", False):
        return
    original = ChatDB.list_groups

    def list_groups(self, keyword: str = "", limit: int = 500, enabled_only: bool = True):
        spec = decode_group_filter(keyword)
        if spec is None:
            return original(self, keyword=keyword, limit=limit, enabled_only=enabled_only)

        rows = original(self, keyword="", limit=max(5000, int(limit)), enabled_only=enabled_only)
        inc = [self._norm(x) for x in spec["include_keywords"] if x]
        exc = [self._norm(x) for x in spec["exclude_keywords"] if x]
        exc_names = {self._norm(x) for x in spec["exclude_names"] if x}
        mode = spec["match_mode"]
        matched = []
        for row in rows:
            name_norm = self._norm(str(row.get("name") or ""))
            hay = self._norm(f"{row.get('name','')} {row.get('tags','')}")
            if inc:
                ok = all(x in hay for x in inc) if mode == "all" else any(x in hay for x in inc)
                if not ok:
                    continue
            if any(x in hay for x in exc):
                continue
            if name_norm in exc_names:
                continue
            matched.append(row)
            if len(matched) >= max(1, int(limit)):
                break
        return matched

    ChatDB.list_groups = list_groups
    ChatDB._yaa_v220_filter_patched = True


def _tool_schemas() -> list[dict]:
    """Tools visible to Qwen. There is deliberately no `respond` tool."""
    empty = {"type": "object", "properties": {}, "required": []}
    return [
        {
            "type": "function",
            "function": {
                "name": "app_status",
                "description": "Read current assistant, Facebook, saved-group, task and backup status. Read-only.",
                "parameters": empty,
            },
        },
        {
            "type": "function",
            "function": {
                "name": "facebook_status",
                "description": "Read cached Facebook connection status. Read-only.",
                "parameters": empty,
            },
        },
        {
            "type": "function",
            "function": {
                "name": "open_facebook_login",
                "description": "Open Facebook only when the user explicitly asks to open Facebook or its sign-in page, so the user can sign in manually. Never enters passwords, 2FA codes, or bypasses checkpoints.",
                "parameters": empty,
            },
        },
        {
            "type": "function",
            "function": {
                "name": "verify_facebook_connection",
                "description": "Verify whether the saved/open Facebook session is signed in. Read-only; use after the user says login is finished.",
                "parameters": empty,
            },
        },
        {
            "type": "function",
            "function": {
                "name": "discover_facebook_groups",
                "description": "Refresh the list of Facebook groups joined by the signed-in account and save them locally. Read-only discovery; it does not publish anything.",
                "parameters": empty,
            },
        },
        {
            "type": "function",
            "function": {
                "name": "search_facebook_groups",
                "description": "Select saved Facebook groups using natural filters. Use include keywords for names/tags that should match; exclude keywords to remove any group containing them; exclude_names for exact group names to omit. Read-only.",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "include_keywords": {"type": "array", "items": {"type": "string"}},
                        "exclude_keywords": {"type": "array", "items": {"type": "string"}},
                        "exclude_names": {"type": "array", "items": {"type": "string"}},
                        "match_mode": {"type": "string", "enum": ["any", "all"], "description": "Whether any or all include keywords must match."},
                        "limit": {"type": "integer", "minimum": 1, "maximum": 500},
                    },
                    "required": [],
                },
            },
        },
        {
            "type": "function",
            "function": {
                "name": "draft_facebook_campaign",
                "description": (
                    "Create a PREVIEW of a Facebook sharing campaign from the user's instruction. "
                    "Use only after the intended groups/source/schedule are understood. This never publishes immediately; "
                    "the desktop app shows the interpreted plan and requires deterministic approval before saving/running it."
                ),
                "parameters": {
                    "type": "object",
                    "properties": {
                        "name": {"type": "string"},
                        "source_page_url": {"type": "string", "description": "Facebook source page URL. Omit/empty to use configured default."},
                        "include_keywords": {"type": "array", "items": {"type": "string"}},
                        "exclude_keywords": {"type": "array", "items": {"type": "string"}},
                        "exclude_names": {"type": "array", "items": {"type": "string"}},
                        "match_mode": {"type": "string", "enum": ["any", "all"]},
                        "weekdays": {"type": "array", "items": {"type": "integer", "minimum": 0, "maximum": 6}, "description": "Monday=0 .. Sunday=6; [] means daily."},
                        "run_time": {"type": "string", "description": "Local 24-hour HH:MM."},
                        "run_once_at": {"type": "string", "description": "Local ISO datetime for a one-time scheduled run, or empty."},
                        "run_immediately": {"type": "boolean", "description": "True only if the user explicitly asks to run/share now."},
                        "post_offset": {"type": "integer", "minimum": 0, "description": "0=latest post, 1=previous, etc."},
                        "max_groups": {"type": "integer", "minimum": 1, "maximum": 500},
                        "interval_seconds": {"type": "integer", "minimum": 30, "maximum": 3600},
                        "no_repeat_days": {"type": "integer", "minimum": 0, "maximum": 365},
                    },
                    "required": [],
                },
            },
        },
        {
            "type": "function",
            "function": {
                "name": "list_tasks",
                "description": "List saved scheduled tasks and their next run. Read-only.",
                "parameters": empty,
            },
        },
        {
            "type": "function",
            "function": {
                "name": "run_facebook_rule_now",
                "description": "Request immediate execution of an existing Facebook task by ID. The app requires user approval before execution.",
                "parameters": {
                    "type": "object",
                    "properties": {"rule_id": {"type": "integer", "minimum": 1}},
                    "required": ["rule_id"],
                },
            },
        },
        {
            "type": "function",
            "function": {
                "name": "backup_status",
                "description": "Read encrypted local-backup and Google Drive sync status. Read-only.",
                "parameters": empty,
            },
        },
    ]


def _install_tool_registry_extensions() -> None:
    from .agent.legacy_smart import SmartPlan
    from .agent.tools import ToolExecution, ToolRegistry

    if getattr(ToolRegistry, "_yaa_v220_patched", False):
        return
    old_init = ToolRegistry.__init__
    old_execute = ToolRegistry.execute

    def __init__(self, db, facebook, backup=None):
        old_init(self, db, facebook, backup)
        self._yaa_db = db
        self._yaa_facebook = facebook
        self._yaa_backup = backup

    def execute(self, name: str, arguments: dict[str, Any] | None = None):
        args = arguments or {}
        if name == "open_facebook_login":
            result = self._yaa_facebook.open_manual_login()
            return ToolExecution(result.ok, result.message, {"count": result.count})
        if name == "verify_facebook_connection":
            result = self._yaa_facebook.verify_session()
            return ToolExecution(result.ok, result.message, {"count": result.count})
        if name == "search_facebook_groups":
            spec = encode_group_filter(
                args.get("include_keywords"), args.get("exclude_keywords"), args.get("exclude_names"), args.get("match_mode", "any")
            )
            limit = max(1, min(int(args.get("limit") or 100), 500))
            rows = self._yaa_db.list_groups(keyword=spec, limit=limit, enabled_only=True)
            payload = {
                "count": len(rows),
                "filter": decode_group_filter(spec),
                "groups": [{"name": g.get("name", ""), "url": g.get("url", "")} for g in rows[:20]],
                "truncated": len(rows) > 20,
            }
            return ToolExecution(True, json.dumps(payload, ensure_ascii=False), payload)
        if name == "approve_facebook_campaign":
            plan_data = args.get("plan") if isinstance(args.get("plan"), dict) else {}
            try:
                plan = SmartPlan(
                    name=str(plan_data.get("name") or "Facebook campaign"),
                    command_text=str(plan_data.get("command_text") or ""),
                    source_page_url=str(plan_data.get("source_page_url") or ""),
                    weekdays=[int(x) for x in (plan_data.get("weekdays") or []) if 0 <= int(x) <= 6],
                    run_time=str(plan_data.get("run_time") or "20:00"),
                    run_once_at=str(plan_data.get("run_once_at") or ""),
                    post_mode="fixed",
                    post_offset=max(0, int(plan_data.get("post_offset") or 0)),
                    group_keyword=str(plan_data.get("group_keyword") or ""),
                    max_groups=max(1, min(int(plan_data.get("max_groups") or 100), 500)),
                    interval_seconds=max(30, int(plan_data.get("interval_seconds") or 60)),
                    no_repeat_days=max(0, int(plan_data.get("no_repeat_days") or 14)),
                    share_mode="native_share",
                )
                rule_id = self._yaa_db.add_rule(plan)
                count = self._yaa_db.count_groups(plan.group_keyword)
                self._yaa_facebook.activity("smart_rule_saved", f"id={rule_id}; groups={count}; {plan.name}")
                run_now = bool(args.get("run_immediately"))
                if run_now:
                    started = self._yaa_facebook.run_rule_now(rule_id)
                    # "Run now" is a one-off action unless the user explicitly
                    # asked for a schedule. Disable the saved rule after handing
                    # the rule snapshot to the background worker so it will not
                    # unexpectedly repeat tomorrow.
                    self._yaa_db.set_rule_enabled(rule_id, False)
                    text = f"Saved one-off task #{rule_id} for {count} matching groups. {started.message}"
                else:
                    text = f"Saved task #{rule_id}. Matching groups: {count}."
                return ToolExecution(True, text, {"rule_id": rule_id, "count": count, "run_immediately": run_now})
            except Exception as exc:
                return ToolExecution(False, f"{type(exc).__name__}: {exc}")
        result = old_execute(self, name, args)
        if name == "app_status" and result.ok:
            result.text = result.text.replace("Hammer=", "Qwen=")
        return result

    ToolRegistry.__init__ = __init__
    ToolRegistry.execute = execute
    ToolRegistry._yaa_v220_patched = True


def _selection_context(db, session_id: int) -> str:
    try:
        session = db.get_session(session_id)
        if not session or not int(session.get("memory_enabled", 1)):
            return ""
        rows = db.list_memory_items(limit=80, enabled_only=True)
    except Exception:
        return ""
    for row in rows:
        if int(row.get("source_session_id") or 0) != int(session_id):
            continue
        if row.get("kind") != "facebook_selection":
            continue
        try:
            data = json.loads(str(row.get("content") or "{}"))
        except Exception:
            continue
        if isinstance(data, dict):
            return json.dumps(data, ensure_ascii=False, separators=(",", ":"))
    return ""


def _save_selection(db, session_id: int, args: dict) -> None:
    data = {
        "include_keywords": _clean_list(args.get("include_keywords")),
        "exclude_keywords": _clean_list(args.get("exclude_keywords")),
        "exclude_names": _clean_list(args.get("exclude_names")),
        "match_mode": "all" if str(args.get("match_mode")).lower() == "all" else "any",
    }
    try:
        session = db.get_session(session_id)
        if session and not int(session.get("memory_enabled", 1)):
            return
        db.add_memory_item("facebook_selection", json.dumps(data, ensure_ascii=False), session_id)
    except Exception:
        pass


def _campaign_preview(controller, user_text: str, args: dict, session_id: int, status=None):
    from .agent.orchestrator import AgentResponse

    include = _clean_list(args.get("include_keywords"))
    exclude_kw = _clean_list(args.get("exclude_keywords"))
    exclude_names = _clean_list(args.get("exclude_names"))
    match_mode = "all" if str(args.get("match_mode")).lower() == "all" else "any"
    encoded = encode_group_filter(include, exclude_kw, exclude_names, match_mode)
    source = str(args.get("source_page_url") or controller.settings.default_source_page or "").strip()
    if not source:
        return AgentResponse(controller.t(
            "فهمت المهمة، لكن ما عندي رابط صفحة Facebook المصدر بعد. أعطني رابط الصفحة التي تريد أخذ المنشور منها.",
            "I understand the task, but I still need the source Facebook page URL.",
        ), used_model=True)

    weekdays = []
    for value in args.get("weekdays") or []:
        try:
            day = int(value)
            if 0 <= day <= 6 and day not in weekdays:
                weekdays.append(day)
        except Exception:
            pass
    run_time = str(args.get("run_time") or "20:00")
    if not __import__("re").match(r"^(?:[01]\d|2[0-3]):[0-5]\d$", run_time):
        run_time = "20:00"
    run_once_at = str(args.get("run_once_at") or "").strip()
    run_immediately = bool(args.get("run_immediately"))
    max_groups = max(1, min(int(args.get("max_groups") or 100), 500))
    interval = max(30, min(int(args.get("interval_seconds") or controller.settings.facebook_interval_min_seconds or 60), 3600))
    no_repeat = max(0, min(int(args.get("no_repeat_days") if args.get("no_repeat_days") is not None else controller.settings.facebook_no_repeat_days), 365))
    post_offset = max(0, int(args.get("post_offset") or 0))
    name = str(args.get("name") or "Facebook campaign")[:120]

    matches = controller.db.list_groups(keyword=encoded, limit=max_groups, enabled_only=True)
    examples = "، ".join(str(g.get("name") or "") for g in matches[:8])
    inc_text = "، ".join(include) if include else controller.t("كل الجروبات", "all groups")
    exc_parts = []
    if exclude_kw:
        exc_parts.append(controller.t("استبعاد أي اسم/وسم يحتوي: ", "exclude keyword(s): ") + "، ".join(exclude_kw))
    if exclude_names:
        exc_parts.append(controller.t("استبعاد أسماء محددة: ", "exclude exact names: ") + "، ".join(exclude_names))
    exclusion = "\n".join(exc_parts) if exc_parts else controller.t("لا توجد استثناءات", "no exclusions")
    schedule = controller.t("تشغيل الآن بعد الموافقة", "run now after approval") if run_immediately else (
        controller.t(f"مرة واحدة: {run_once_at}", f"one time: {run_once_at}") if run_once_at else controller.t(f"الساعة {run_time}", f"at {run_time}")
    )
    post_text = controller.t("آخر منشور", "latest post") if post_offset == 0 else controller.t(f"المنشور السابق رقم {post_offset}", f"post offset {post_offset}")
    summary = controller.t(
        f"فهمت المهمة هكذا:\n"
        f"• المصدر: {source}\n"
        f"• اختيار الجروبات: {inc_text}\n"
        f"• {exclusion}\n"
        f"• المطابق الآن: {len(matches)} جروب (حد التنفيذ {max_groups})\n"
        + (f"• أمثلة: {examples}\n" if examples else "")
        + f"• المنشور: {post_text}\n"
        f"• الموعد: {schedule}\n"
        f"• الفاصل: {interval} ثانية — منع التكرار: {no_repeat} يوم\n\n"
        "هذه معاينة ولم يتم نشر شيء. راجع التفاصيل واضغط زر «موافق» للتنفيذ.",
        f"I understood the task as follows:\n"
        f"• Source: {source}\n"
        f"• Group selection: {inc_text}\n"
        f"• {exclusion}\n"
        f"• Currently matching: {len(matches)} group(s) (execution cap {max_groups})\n"
        + (f"• Examples: {examples}\n" if examples else "")
        + f"• Post: {post_text}\n"
        f"• Schedule: {schedule}\n"
        f"• Interval: {interval}s — no-repeat: {no_repeat} day(s)\n\n"
        "This is only a preview; nothing was published. Review it and click Approve to execute.",
    )

    plan = {
        "name": name,
        "command_text": user_text,
        "source_page_url": source,
        "weekdays": weekdays,
        "run_time": run_time,
        "run_once_at": run_once_at,
        "post_mode": "fixed",
        "post_offset": post_offset,
        "group_keyword": encoded,
        "max_groups": max_groups,
        "interval_seconds": interval,
        "no_repeat_days": no_repeat,
        "share_mode": "native_share",
    }
    controller.db.set_pending_action(
        session_id,
        "approve_facebook_campaign",
        {"plan": plan, "run_immediately": run_immediately},
        summary,
    )
    controller._activity("agent_plan_preview", f"personal-agent groups={len(matches)}; {name}", status,
                         controller.t("الخطة جاهزة وتنتظر موافقتك", "Plan ready and waiting for approval"))
    return AgentResponse(summary, used_model=True, used_tools=True, detail=json.dumps(plan, ensure_ascii=False))


def _install_personal_controller() -> None:
    from .agent.orchestrator import (
        AgentResponse,
        SmartAgentController,
        _CANCEL_RE,
        _CONFIRM_RE,
    )
    from .ai.profiles import QWEN

    if getattr(SmartAgentController, "_yaa_v220_patched", False):
        return

    safe_tools = {
        "app_status",
        "facebook_status",
        "open_facebook_login",
        "verify_facebook_connection",
        "discover_facebook_groups",
        "search_facebook_groups",
        "list_tasks",
        "backup_status",
    }

    def handle(self, profile, history: list[dict], user_text: str, session_id: int,
               max_tokens: int, timeout: int, status=None):
        text = (user_text or "").strip()
        if not text:
            return AgentResponse("")

        pending = self.db.get_pending_action(session_id)
        normalized = " ".join(text.split())
        if pending and _CANCEL_RE.match(normalized):
            self.db.clear_pending_action(session_id)
            self._activity("agent_action_cancelled", pending.get("summary", ""), status,
                           self.t("تم إلغاء العملية", "Action cancelled"))
            return AgentResponse(self.t("تمام، ألغيت العملية المعلّقة.", "Cancelled the pending action."), used_tools=True)

        if pending and _CONFIRM_RE.match(normalized):
            self._activity("agent_action_confirmed", pending.get("tool_name", ""), status,
                           self.t("تمت الموافقة — جاري التنفيذ", "Approved — executing"))
            result = self.tools.execute(pending["tool_name"], pending.get("arguments") or {})
            self.db.clear_pending_action(session_id)
            self._activity("agent_action_executed" if result.ok else "agent_action_error", result.text)
            prompt = self.t(
                f"هذه نتيجة الإجراء الذي وافق عليه المستخدم: {result.text}\nاشرحها باختصار وبدون اختراع أي شيء.",
                f"The approved application action returned: {result.text}\nExplain it briefly without inventing anything.",
            )
            try:
                natural = self.chat_engine.reply(QWEN, history, prompt, max_tokens, timeout, status=status).text
            except Exception:
                natural = result.text
            return AgentResponse(natural, used_model=True, used_tools=True, detail=result.text)

        if pending:
            # Natural edits/corrections while a plan is waiting are handled by Qwen
            # with the pending preview included as context rather than blindly
            # treating every message as approval.
            pending_note = self.t(
                "هناك خطة معلقة لم يعتمدها المستخدم بعد. إذا كانت الرسالة تعديلاً للخطة، أنشئ draft_facebook_campaign جديدًا يعكس التعديل.\nالخطة الحالية:\n",
                "There is an unapproved pending plan. If the message edits it, create a new draft_facebook_campaign reflecting the edit.\nCurrent plan:\n",
            ) + str(pending.get("summary") or "")
        else:
            pending_note = ""

        selection = _selection_context(self.db, session_id)
        now = datetime.now().astimezone().isoformat(timespec="seconds")
        system_context = (
            "/no_think\n"
            "You are a direct personal assistant. Normal conversation MUST be answered as normal assistant text; do not call a fake respond function. "
            "Use application tools only when they materially help complete the user's request. You may use multiple safe tools across successive turns. "
            "For Facebook group requests, prefer discover_facebook_groups before search if the saved list may be stale. "
            "When the user describes group inclusion/exclusion in natural Arabic, map it faithfully to include_keywords, exclude_keywords, and exact exclude_names. "
            "Never claim an action succeeded unless a tool result confirms it. Publishing or immediate campaign execution must go through draft_facebook_campaign and the app approval gate. "
            "Facebook passwords, 2FA and checkpoints are always manual; open the login page when needed, never attempt to bypass them. "
            f"Current local datetime: {now}. Configured default Facebook source page: {self.settings.default_source_page or '(none)'}. "
            f"Saved Facebook groups: {self.db.count_groups()}."
        )
        if selection:
            system_context += f" Current group selection in this chat: {selection}. Reuse it when the user says 'these groups', 'اعتمدهم', or an equivalent reference."
        if pending_note:
            system_context += "\n" + pending_note

        messages = [self._preference_context(), {"role": "system", "content": system_context}] + list(history)
        messages.append({"role": "user", "content": text[:5000]})
        tools = _tool_schemas()
        used_tools = False
        last_detail = ""

        for _step in range(5):
            self._activity("qwen_analyzing", text[:500], status, self.t("Qwen يفهم الطلب", "Qwen is handling the request"))
            turn = self.chat_engine.runtime.native_turn(
                QWEN, messages, tools=tools, max_tokens=max_tokens, timeout=timeout, status=status
            )
            calls = turn.get("tool_calls") if isinstance(turn.get("tool_calls"), list) else []
            if not calls:
                answer = str(turn.get("content") or "").strip()
                if not answer:
                    answer = self.chat_engine.reply(QWEN, history, text, max_tokens, timeout, status=status).text
                return AgentResponse(answer, used_model=True, used_tools=used_tools, detail=last_detail)

            call = calls[0]
            name = str(call.get("name") or "").strip()
            args = call.get("arguments") if isinstance(call.get("arguments"), dict) else {}
            call_id = str(call.get("id") or "call")
            self._activity("qwen_tool_selected", f"{name}; args={args}")

            if name == "draft_facebook_campaign":
                # If the user refers to a previously selected group set and Qwen
                # omitted filters, carry that selection forward deterministically.
                if not any(args.get(k) for k in ("include_keywords", "exclude_keywords", "exclude_names")) and selection:
                    try:
                        saved = json.loads(selection)
                        for key in ("include_keywords", "exclude_keywords", "exclude_names", "match_mode"):
                            if key in saved and key not in args:
                                args[key] = saved[key]
                    except Exception:
                        pass
                self.db.clear_pending_action(session_id)
                return _campaign_preview(self, text, args, session_id, status=status)

            if name == "run_facebook_rule_now":
                try:
                    rule_id = int(args.get("rule_id"))
                except Exception:
                    rule_id = 0
                if not rule_id:
                    messages.extend([
                        {"role": "assistant", "content": turn.get("content") or "", "tool_calls": [call]},
                        {"role": "tool", "tool_call_id": call_id, "name": name, "content": "Invalid task ID."},
                    ])
                    continue
                summary = self.t(f"سأشغّل المهمة رقم {rule_id} الآن. هل تريد التنفيذ؟",
                                 f"I will run task #{rule_id} now. Approve?")
                self.db.set_pending_action(session_id, "run_facebook_rule_now", {"rule_id": rule_id}, summary)
                return AgentResponse(summary, used_model=True, used_tools=True, detail=f"rule={rule_id}")

            if name not in safe_tools:
                tool_text = f"Unknown or disallowed tool: {name}"
                ok = False
            else:
                result = self.tools.execute(name, args)
                used_tools = True
                ok = result.ok
                tool_text = result.text
                last_detail = f"{name}: {tool_text}"
                self._activity("qwen_tool_result", last_detail, status,
                               self.t("تمت قراءة نتيجة الأداة", "Tool result received"))
                if name == "search_facebook_groups" and result.ok:
                    _save_selection(self.db, session_id, args)
                    selection = json.dumps({
                        "include_keywords": _clean_list(args.get("include_keywords")),
                        "exclude_keywords": _clean_list(args.get("exclude_keywords")),
                        "exclude_names": _clean_list(args.get("exclude_names")),
                        "match_mode": "all" if str(args.get("match_mode")).lower() == "all" else "any",
                    }, ensure_ascii=False, separators=(",", ":"))

            # Feed the concrete result back to Qwen so it can either call another
            # safe tool or answer the user naturally.
            messages.append({
                "role": "assistant",
                "content": str(turn.get("content") or ""),
                "tool_calls": [{
                    "id": call_id,
                    "type": "function",
                    "function": {
                        "name": name,
                        "arguments": json.dumps(args, ensure_ascii=False, separators=(",", ":")),
                    },
                }],
            })
            messages.append({
                "role": "tool",
                "tool_call_id": call_id,
                "name": name,
                "content": tool_text if ok else f"ERROR: {tool_text}",
            })

        # A five-step cap prevents accidental local-agent loops. We still return
        # a useful direct answer rather than leaving the user with silence.
        fallback_prompt = self.t(
            "وصلت لحد خطوات الأدوات لهذه الرسالة. لخّص ما تم فعله وما الذي يحتاجه المستخدم بعد ذلك اعتمادًا فقط على النتائج أعلاه.",
            "The tool-step limit was reached. Summarize what was completed and what the user should do next, using only the results above.",
        )
        try:
            answer = self.chat_engine.reply(QWEN, [], fallback_prompt + "\n" + last_detail, max_tokens, timeout, status=status).text
        except Exception:
            answer = last_detail or self.t("لم أستطع إكمال كل الخطوات في طلب واحد.", "I could not complete every step in one request.")
        return AgentResponse(answer, used_model=True, used_tools=used_tools, detail=last_detail)

    SmartAgentController.handle = handle
    SmartAgentController._yaa_v220_patched = True


def apply_personal_assistant() -> None:
    global _APPLIED
    if _APPLIED:
        return
    _install_group_filtering()
    _install_tool_registry_extensions()
    _install_personal_controller()
    _APPLIED = True
