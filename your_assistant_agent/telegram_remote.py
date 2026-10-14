from __future__ import annotations

import secrets
import threading
import time
from typing import Any, Callable

import requests

from .db import Database
from .security import SecurityManager
from .smart_agent import SmartPlanner, SmartPlannerError


class TelegramRemote(threading.Thread):
    """Private Telegram remote control using Bot API long polling.

    Only the configured Telegram numeric user ID is accepted. Sensitive actions
    are staged and require an inline Approve button before execution.
    """

    def __init__(self, db: Database, security: SecurityManager, command_cb: Callable[[str, Any], None]):
        super().__init__(name="YourAssistantAgentTelegram", daemon=True)
        self.db = db
        self.security = security
        self.command_cb = command_cb
        self.stop_event = threading.Event()
        self.offset = 0
        self.pending: dict[str, dict] = {}
        self.session = requests.Session()
        self._last_config_error = ""

    def shutdown(self):
        self.stop_event.set()

    def _config(self) -> tuple[bool, str, str]:
        enabled = bool(self.db.get_setting("telegram_enabled", False))
        user_id = str(self.db.get_setting("telegram_authorized_user_id", "") or "").strip()
        token = self.security.get_secret("telegram_bot_token") if enabled else ""
        return enabled, token, user_id

    @staticmethod
    def _base(token: str) -> str:
        return f"https://api.telegram.org/bot{token}"

    def _api(self, token: str, method: str, *, params=None, json=None, timeout=25):
        r = self.session.post(f"{self._base(token)}/{method}", params=params, json=json, timeout=timeout)
        r.raise_for_status()
        data = r.json()
        if not data.get("ok"):
            raise RuntimeError(data.get("description") or f"Telegram {method} failed")
        return data.get("result")

    def send_message(self, token: str, chat_id: str | int, text: str, buttons: list[tuple[str, str]] | None = None):
        payload: dict[str, Any] = {"chat_id": chat_id, "text": text[:3900]}
        if buttons:
            payload["reply_markup"] = {
                "inline_keyboard": [[{"text": label, "callback_data": data} for label, data in buttons]]
            }
        return self._api(token, "sendMessage", json=payload)

    def send_test(self) -> tuple[bool, str]:
        enabled, token, user_id = self._config()
        if not enabled:
            return False, "Telegram Remote is disabled."
        if not token or not user_id:
            return False, "Bot token and authorized Telegram User ID are required."
        try:
            self.send_message(token, user_id, "Your Assistant Agent ✅ Telegram Remote connected.")
            return True, "Telegram test message sent."
        except Exception as exc:
            return False, str(exc)

    def run(self):
        self.db.audit("INFO", "telegram_remote_started")
        while not self.stop_event.is_set():
            enabled, token, user_id = self._config()
            if not enabled or not token or not user_id:
                self.stop_event.wait(2.0)
                continue
            try:
                result = self._api(
                    token,
                    "getUpdates",
                    params={"offset": self.offset, "timeout": 18, "allowed_updates": '["message","callback_query"]'},
                    timeout=23,
                )
                self._last_config_error = ""
                for update in result or []:
                    self.offset = max(self.offset, int(update.get("update_id", 0)) + 1)
                    self._handle_update(token, user_id, update)
            except Exception as exc:
                msg = str(exc)
                if msg != self._last_config_error:
                    self.db.audit("ERROR", "telegram_remote_error", msg)
                    self._last_config_error = msg
                self.stop_event.wait(5.0)
        self.db.audit("INFO", "telegram_remote_stopped")

    @staticmethod
    def _sender_id(update: dict) -> str:
        if "callback_query" in update:
            return str((update.get("callback_query") or {}).get("from", {}).get("id", ""))
        return str((update.get("message") or {}).get("from", {}).get("id", ""))

    def _handle_update(self, token: str, authorized_user_id: str, update: dict):
        sender = self._sender_id(update)
        if sender != str(authorized_user_id):
            if sender:
                self.db.audit("SECURITY", "telegram_unauthorized_user", sender)
            return
        if "callback_query" in update:
            self._handle_callback(token, update["callback_query"])
            return
        message = update.get("message") or {}
        text = str(message.get("text") or "").strip()
        chat_id = message.get("chat", {}).get("id")
        if not text or chat_id is None:
            return
        self._handle_text(token, chat_id, text)

    def _status_text(self, language: str) -> str:
        paused = bool(self.db.get_setting("paused", False))
        fb = str(self.db.get_setting("facebook_connection_status", "not_checked") or "not_checked")
        smart = self.db.smart_queue_stats()
        rules = len([r for r in self.db.list_smart_rules() if r["enabled"]])
        if language == "ar":
            return (
                f"حالة الوكيل: {'متوقف مؤقتًا' if paused else 'يعمل'}\n"
                f"Facebook: {fb}\n"
                f"القواعد الذكية المفعلة: {rules}\n"
                f"طابور Smart: {smart or 'فارغ'}"
            )
        return f"Agent: {'paused' if paused else 'running'}\nFacebook: {fb}\nEnabled smart rules: {rules}\nSmart queue: {smart or 'empty'}"

    def _rules_text(self, language: str) -> str:
        rows = self.db.list_smart_rules()
        if not rows:
            return "لا توجد قواعد ذكية بعد." if language == "ar" else "No smart rules yet."
        parts = []
        for r in rows[:30]:
            state = "ON" if r["enabled"] else "OFF"
            parts.append(f"#{r['id']} [{state}] {r['name']} — {r['next_run_at'] or '—'}")
        return "\n".join(parts)

    def _handle_text(self, token: str, chat_id: int, text: str):
        language = str(self.db.get_setting("language", "ar") or "ar")
        cmd = text.casefold().strip()
        if cmd in {"/start", "/help", "مساعدة", "مساعده"}:
            help_text = (
                "الأوامر: /status الحالة، /rules القواعد، /run 3 تشغيل قاعدة، /pause إيقاف مؤقت، /resume استئناف، /stop إيقاف طارئ.\n"
                "أو اكتب أمر حملة طبيعي مثل: كل اثنين الساعة 8 مساء خذ آخر بوست وانشره على الجروبات اللي اسمها يحتوي الفحيص كل نص دقيقة."
                if language == "ar" else
                "Commands: /status, /rules, /run 3, /pause, /resume, /stop. Or type a natural-language campaign instruction."
            )
            self.send_message(token, chat_id, help_text)
            return
        if cmd in {"/status", "الحالة", "حاله", "الحاله"}:
            self.send_message(token, chat_id, self._status_text(language)); return
        if cmd in {"/rules", "القواعد"}:
            self.send_message(token, chat_id, self._rules_text(language)); return
        if cmd in {"/pause", "وقف مؤقت", "ايقاف مؤقت", "إيقاف مؤقت"}:
            self.command_cb("pause")
            self.send_message(token, chat_id, "تم إيقاف الوكيل مؤقتًا." if language == "ar" else "Agent paused.")
            return
        if cmd in {"/resume", "استئناف", "كمل", "كمّل"}:
            self.command_cb("resume")
            self.send_message(token, chat_id, "تم استئناف الوكيل." if language == "ar" else "Agent resumed.")
            return
        if cmd.startswith("/run"):
            parts = cmd.split()
            if len(parts) != 2 or not parts[1].isdigit() or not self.db.get_smart_rule(int(parts[1])):
                self.send_message(token, chat_id, "استخدم /run ثم رقم القاعدة، مثال /run 3" if language == "ar" else "Use /run RULE_ID, e.g. /run 3")
                return
            self._stage(token, chat_id, "run_rule", {"rule_id": int(parts[1])}, f"تشغيل القاعدة #{parts[1]} الآن؟" if language == "ar" else f"Run rule #{parts[1]} now?")
            return
        if cmd in {"/stop", "ايقاف طارئ", "إيقاف طارئ"}:
            self._stage(token, chat_id, "emergency_stop", {}, "تأكيد الإيقاف الطارئ وإلغاء العناصر المعلقة؟" if language == "ar" else "Confirm emergency stop and cancel pending items?")
            return

        planner = SmartPlanner(language)
        try:
            plans = planner.parse_many(
                text,
                default_source_page=str(self.db.get_setting("smart_default_source_page", "") or ""),
                default_interval=int(self.db.get_setting("smart_default_interval_seconds", 60) or 60),
                default_max_groups=int(self.db.get_setting("smart_default_max_groups", 100) or 100),
                default_no_repeat_days=int(self.db.get_setting("smart_no_repeat_days", 14) or 14),
            )
        except SmartPlannerError as exc:
            self.send_message(token, chat_id, str(exc)); return
        blocks = []
        for i, plan in enumerate(plans, 1):
            blocks.append((f"#{i}\n" if len(plans) > 1 else "") + plan.summary(language))
        summary = ("فهمت الأمر هكذا:\n\n" if language == "ar" else "I understood the instruction as:\n\n") + "\n\n---\n\n".join(blocks)
        self._stage(token, chat_id, "create_rule", {"plans": [p.to_dict() for p in plans]}, summary)

    def _stage(self, token: str, chat_id: int, kind: str, data: dict, text: str):
        key = secrets.token_hex(4)
        self.pending[key] = {"kind": kind, "data": data, "chat_id": chat_id, "created": time.time()}
        # prune old pending actions
        for old_key, item in list(self.pending.items()):
            if time.time() - float(item.get("created", 0)) > 1800:
                self.pending.pop(old_key, None)
        self.send_message(token, chat_id, text, [("✅ Approve", f"approve:{key}"), ("❌ Cancel", f"cancel:{key}")])

    def _handle_callback(self, token: str, callback: dict):
        callback_id = callback.get("id")
        data = str(callback.get("data") or "")
        message = callback.get("message") or {}
        chat_id = message.get("chat", {}).get("id")
        try:
            if callback_id:
                self._api(token, "answerCallbackQuery", json={"callback_query_id": callback_id})
        except Exception:
            pass
        if ":" not in data or chat_id is None:
            return
        action, key = data.split(":", 1)
        item = self.pending.pop(key, None)
        if not item or int(item.get("chat_id")) != int(chat_id):
            self.send_message(token, chat_id, "This approval request expired.")
            return
        language = str(self.db.get_setting("language", "ar") or "ar")
        if action == "cancel":
            self.send_message(token, chat_id, "تم الإلغاء." if language == "ar" else "Cancelled.")
            return
        if action != "approve":
            return
        kind = item["kind"]
        payload = item["data"]
        if kind == "create_rule":
            plans = payload.get("plans") or ([payload["plan"]] if payload.get("plan") else [])
            ids = [self.db.add_smart_rule(plan) for plan in plans]
            label = ", ".join(str(x) for x in ids)
            self.send_message(token, chat_id, f"تم اعتماد القواعد الذكية: {label}." if language == "ar" else f"Smart rules approved: {label}.")
        elif kind == "run_rule":
            self.command_cb("run_smart_rule_now", int(payload["rule_id"]))
            self.send_message(token, chat_id, "تم إرسال أمر التشغيل." if language == "ar" else "Run command queued.")
        elif kind == "emergency_stop":
            self.command_cb("emergency_stop")
            self.send_message(token, chat_id, "تم تنفيذ الإيقاف الطارئ." if language == "ar" else "Emergency stop executed.")
