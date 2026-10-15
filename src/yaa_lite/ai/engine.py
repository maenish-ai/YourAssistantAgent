from __future__ import annotations

from dataclasses import dataclass

from .profiles import AgentProfile
from .runtime import LocalAIRuntime


@dataclass
class Reply:
    text: str
    used_model: bool


def quick_reply(user_text: str) -> str | None:
    """Deprecated compatibility hook.

    v2 intentionally returns None so even greetings are handled by Hammer.
    """
    return None


class ChatEngine:
    def __init__(self, runtime: LocalAIRuntime):
        self.runtime = runtime

    def reply(self, profile: AgentProfile, history: list[dict], user_text: str,
              max_tokens: int, timeout: int, status=None) -> Reply:
        compact = history[-8:] + [{"role": "user", "content": user_text[:3000]}]
        return Reply(
            self.runtime.chat(profile, compact, max_tokens=max_tokens, timeout=timeout, status=status),
            used_model=True,
        )
