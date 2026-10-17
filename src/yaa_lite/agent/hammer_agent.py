from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from ..ai.profiles import QWEN
from ..ai.runtime import LocalAIRuntime

PRIMARY_MODEL_LABEL = "Qwen3 1.7B Q4_K_M"
PRIMARY_MODEL_LICENSE = "Apache-2.0"
# Compatibility names retained for older imports.
HAMMER_MODEL_LABEL = PRIMARY_MODEL_LABEL
HAMMER_LICENSE = PRIMARY_MODEL_LICENSE


@dataclass
class HammerDecision:
    name: str
    arguments: dict[str, Any]
    content: str = ""


class HammerAgentRouter:
    """Compatibility-named router backed by Qwen3.

    The application remains the safety and permission boundary. Qwen chooses
    from an explicit allow-list; arbitrary Python or shell execution is never
    exposed to the model.
    """

    def __init__(self, runtime: LocalAIRuntime):
        self.runtime = runtime

    @staticmethod
    def tool_schemas() -> list[dict]:
        return [
            {
                "type": "function",
                "function": {
                    "name": "respond",
                    "description": "Normal conversation, greetings, explanations, and requests that need no application action. Reply naturally in the user's language.",
                    "parameters": {
                        "type": "object",
                        "properties": {"message": {"type": "string", "description": "Final natural-language reply"}},
                        "required": ["message"],
                    },
                },
            },
            {
                "type": "function",
                "function": {
                    "name": "app_status",
                    "description": "Read compact status for the AI, Facebook, saved groups, tasks and backup.",
                    "parameters": {"type": "object", "properties": {}, "required": []},
                },
            },
            {
                "type": "function",
                "function": {
                    "name": "list_tasks",
                    "description": "List saved scheduled tasks and their next-run state.",
                    "parameters": {"type": "object", "properties": {}, "required": []},
                },
            },
            {
                "type": "function",
                "function": {
                    "name": "backup_status",
                    "description": "Read encrypted backup and Google Drive sync status.",
                    "parameters": {"type": "object", "properties": {}, "required": []},
                },
            },
            {
                "type": "function",
                "function": {
                    "name": "prepare_facebook_campaign",
                    "description": "Prepare or edit a Facebook group-sharing campaign from natural language. Do not claim it executed; the app previews sensitive actions before approval.",
                    "parameters": {
                        "type": "object",
                        "properties": {"instruction": {"type": "string", "description": "Complete instruction preserving time, source page and group filter wording"}},
                        "required": ["instruction"],
                    },
                },
            },
            {
                "type": "function",
                "function": {
                    "name": "count_facebook_groups",
                    "description": "Count saved Facebook groups matching a name/tag keyword. Empty keyword means all saved groups.",
                    "parameters": {
                        "type": "object",
                        "properties": {"keyword": {"type": "string", "description": "Group keyword, or empty string"}},
                        "required": ["keyword"],
                    },
                },
            },
            {
                "type": "function",
                "function": {
                    "name": "facebook_status",
                    "description": "Read Facebook connection status without publishing anything.",
                    "parameters": {"type": "object", "properties": {}, "required": []},
                },
            },
            {
                "type": "function",
                "function": {
                    "name": "discover_facebook_groups",
                    "description": "Refresh joined Facebook groups. This uses the Facebook connection and requires approval.",
                    "parameters": {"type": "object", "properties": {}, "required": []},
                },
            },
            {
                "type": "function",
                "function": {
                    "name": "run_facebook_rule_now",
                    "description": "Run an existing saved Facebook task now. Requires approval.",
                    "parameters": {
                        "type": "object",
                        "properties": {"rule_id": {"type": "integer", "description": "Saved task ID"}},
                        "required": ["rule_id"],
                    },
                },
            },
        ]

    def decide(self, history: list[dict], user_text: str, max_tokens: int, timeout: int, status=None) -> HammerDecision:
        # Tool routing gets a shorter history than normal chat so the schemas fit
        # comfortably in the low-memory context window.
        messages = history[-5:] + [{"role": "user", "content": user_text[:2800]}]
        raw = self.runtime.tool_call(
            QWEN, messages, tools=self.tool_schemas(), max_tokens=max_tokens, timeout=timeout, status=status
        )
        name = str(raw.get("name") or "respond")
        args = raw.get("arguments") if isinstance(raw.get("arguments"), dict) else {}
        content = str(raw.get("content") or "")
        return HammerDecision(name=name, arguments=args, content=content)
