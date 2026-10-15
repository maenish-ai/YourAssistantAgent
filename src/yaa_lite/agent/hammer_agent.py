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
    """Dedicated local action-model router.

    Hammer does not execute arbitrary Python. It only selects from this explicit
    allow-list. The controller remains the authority for confirmation and actual
    execution.
    """

    def __init__(self, runtime: LocalAIRuntime):
        self.runtime = runtime

    @staticmethod
    def tool_schemas() -> list[dict]:
        # Hammer's model card recommends an explicit respond() function so
        # irrelevant/non-action messages can still be answered naturally.
        return [
            {
                "type": "function",
                "function": {
                    "name": "respond",
                    "description": (
                        "Use this for ordinary conversation or whenever no external tool is needed. "
                        "Reply in the same language as the user."
                    ),
                    "parameters": {
                        "type": "object",
                        "properties": {
                            "message": {"type": "string", "description": "Natural assistant reply to the user"}
                        },
                        "required": ["message"],
                    },
                },
            },
            {
                "type": "function",
                "function": {
                    "name": "prepare_facebook_campaign",
                    "description": (
                        "Prepare a Facebook sharing campaign from a natural-language instruction. "
                        "Use this when the user wants to publish/share/schedule a page post to groups. "
                        "Do not claim it executed; the app will preview and ask for confirmation."
                    ),
                    "parameters": {
                        "type": "object",
                        "properties": {
                            "instruction": {"type": "string", "description": "The complete user instruction, preserving date/time/group wording"}
                        },
                        "required": ["instruction"],
                    },
                },
            },
            {
                "type": "function",
                "function": {
                    "name": "count_facebook_groups",
                    "description": "Count saved Facebook groups whose name or tag contains a keyword.",
                    "parameters": {
                        "type": "object",
                        "properties": {
                            "keyword": {"type": "string", "description": "Group keyword. Empty string means all saved groups."}
                        },
                        "required": ["keyword"],
                    },
                },
            },
            {
                "type": "function",
                "function": {
                    "name": "facebook_status",
                    "description": "Read the cached Facebook connection status without opening the browser.",
                    "parameters": {"type": "object", "properties": {}, "required": []},
                },
            },
            {
                "type": "function",
                "function": {
                    "name": "discover_facebook_groups",
                    "description": "Open the saved Facebook session and discover the groups joined by the account. Requires user confirmation.",
                    "parameters": {"type": "object", "properties": {}, "required": []},
                },
            },
            {
                "type": "function",
                "function": {
                    "name": "run_facebook_rule_now",
                    "description": "Run an existing saved Facebook sharing rule immediately. Requires user confirmation.",
                    "parameters": {
                        "type": "object",
                        "properties": {
                            "rule_id": {"type": "integer", "description": "Saved rule ID"}
                        },
                        "required": ["rule_id"],
                    },
                },
            },
        ]

    def decide(
        self,
        history: list[dict],
        user_text: str,
        max_tokens: int,
        timeout: int,
        status=None,
    ) -> HammerDecision:
        messages = history[-6:] + [{"role": "user", "content": user_text[:3500]}]
        raw = self.runtime.tool_call(
            HAMMER,
            messages,
            tools=self.tool_schemas(),
            max_tokens=max_tokens,
            timeout=timeout,
            status=status,
        )
        name = str(raw.get("name") or "respond")
        args = raw.get("arguments") if isinstance(raw.get("arguments"), dict) else {}
        content = str(raw.get("content") or "")
        return HammerDecision(name=name, arguments=args, content=content)
