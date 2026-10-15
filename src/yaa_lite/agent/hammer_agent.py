from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from ..ai.profiles import HAMMER
from ..ai.runtime import LocalAIRuntime

HAMMER_MODEL_LABEL = "Hammer 2.1 0.5B Q4_K_M"
HAMMER_LICENSE = "CC-BY-NC-4.0"


@dataclass
class HammerDecision:
    name: str
    arguments: dict[str, Any]
    content: str = ""


class HammerAgentRouter:
    """Hammer is the only conversational/reasoning model in v2.0.

    It never receives arbitrary Python execution. It chooses one item from an
    explicit allow-list and the application remains the safety/permission
    boundary around external actions.
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
                    "description": "Use for normal conversation, greetings, explanations, and any request that does not require an application tool. Reply naturally in the user's language.",
                    "parameters": {
                        "type": "object",
                        "properties": {"message": {"type": "string", "description": "The final natural-language reply"}},
                        "required": ["message"],
                    },
                },
            },
            {
                "type": "function",
                "function": {
                    "name": "app_status",
                    "description": "Read a compact status summary for Hammer, Facebook, saved groups, tasks and backup.",
                    "parameters": {"type": "object", "properties": {}, "required": []},
                },
            },
            {
                "type": "function",
                "function": {
                    "name": "list_tasks",
                    "description": "List saved scheduled tasks and their next run state.",
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
                    "description": "Prepare or edit a Facebook group-sharing campaign from the user's natural-language instruction. Do not claim it executed. The app previews sensitive actions before approval.",
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
                    "description": "Read Facebook connection status without performing a publish action.",
                    "parameters": {"type": "object", "properties": {}, "required": []},
                },
            },
            {
                "type": "function",
                "function": {
                    "name": "discover_facebook_groups",
                    "description": "Refresh joined Facebook groups. This opens/uses the Facebook browser connection and requires approval.",
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
        messages = history[-8:] + [{"role": "user", "content": user_text[:3500]}]
        raw = self.runtime.tool_call(
            HAMMER, messages, tools=self.tool_schemas(), max_tokens=max_tokens, timeout=timeout, status=status
        )
        name = str(raw.get("name") or "respond")
        args = raw.get("arguments") if isinstance(raw.get("arguments"), dict) else {}
        content = str(raw.get("content") or "")
        return HammerDecision(name=name, arguments=args, content=content)
