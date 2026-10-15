from __future__ import annotations

import re
from dataclasses import dataclass

from .profiles import AgentProfile
from .runtime import LocalAIRuntime


@dataclass
class Reply:
    text: str
    used_model: bool


_FAST_AR = {
    "كيف حالك": "تمام، جاهز معك. شو بدك نعمل؟",
    "مرحبا": "أهلًا! شو بدك نعمل اليوم؟",
    "السلام عليكم": "وعليكم السلام. شو بدك أساعدك فيه؟",
}
_FAST_EN = {"hi": "Hi! What would you like to do?", "hello": "Hello! What would you like to do?"}


class ChatEngine:
    def __init__(self, runtime: LocalAIRuntime):
        self.runtime = runtime

    def reply(self, profile: AgentProfile, history: list[dict], user_text: str,
              max_tokens: int, timeout: int, status=None) -> Reply:
        normalized = re.sub(r"[؟?!.,،]+$", "", user_text.strip().lower())
        if normalized in _FAST_AR:
            return Reply(_FAST_AR[normalized], used_model=False)
        if normalized in _FAST_EN:
            return Reply(_FAST_EN[normalized], used_model=False)
        # Keep the prompt small on 4 GB machines: last 8 turns only.
        compact = history[-8:] + [{"role": "user", "content": user_text[:3000]}]
        return Reply(
            self.runtime.chat(profile, compact, max_tokens=max_tokens, timeout=timeout, status=status),
            used_model=True,
        )
