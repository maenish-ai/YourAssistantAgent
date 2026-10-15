from __future__ import annotations

import re
from dataclasses import dataclass

from .profiles import AgentProfile
from .runtime import LocalAIRuntime


@dataclass
class Reply:
    text: str
    used_model: bool


def _normalize(text: str) -> str:
    text = text.strip().lower()
    text = re.sub(r"[؟?!.,،؛:]+$", "", text)
    text = re.sub(r"\s+", " ", text)
    # Light Arabic normalization for common conversational forms.
    text = text.translate(str.maketrans({"أ": "ا", "إ": "ا", "آ": "ا", "ى": "ي"}))
    return text.strip()


_FAST_AR = {
    "كيف حالك": "تمام، جاهز معك. شو بدك نعمل؟",
    "كيفك": "تمام، جاهز معك. شو بدك نعمل؟",
    "شو اخبارك": "تمام، جاهز. احكيلي شو بدك أعمل.",
    "مرحبا": "أهلًا! شو بدك نعمل اليوم؟",
    "اهلا": "أهلًا وسهلًا! احكيلي شو بدك نعمل.",
    "هلا": "هلا فيك! شو بدك أساعدك فيه؟",
    "هاي": "أهلًا! شو بدك نعمل؟",
    "الو": "معك، احكيلي شو بدك.",
    "السلام عليكم": "وعليكم السلام. شو بدك أساعدك فيه؟",
    "انت مين": "أنا Your Assistant Agent، مساعدك المحلي على الكمبيوتر. احكيلي المهمة بشكل طبيعي وأنا بفهمها وبجهزها معك.",
    "مين انت": "أنا Your Assistant Agent، مساعدك المحلي على الكمبيوتر. احكيلي المهمة بشكل طبيعي وأنا بفهمها وبجهزها معك.",
}
_FAST_EN = {
    "hi": "Hi! What would you like to do?",
    "hello": "Hello! What would you like to do?",
    "how are you": "I'm ready. What would you like me to do?",
    "who are you": "I'm Your Assistant Agent, your local desktop assistant. Tell me the task naturally and I'll work through it with you.",
}


class ChatEngine:
    def __init__(self, runtime: LocalAIRuntime):
        self.runtime = runtime

    def reply(
        self,
        profile: AgentProfile,
        history: list[dict],
        user_text: str,
        max_tokens: int,
        timeout: int,
        status=None,
    ) -> Reply:
        normalized = _normalize(user_text)
        if normalized in _FAST_AR:
            return Reply(_FAST_AR[normalized], used_model=False)
        if normalized in _FAST_EN:
            return Reply(_FAST_EN[normalized], used_model=False)

        # Keep the prompt small on 4 GB machines: last 8 turns only.
        compact = history[-8:] + [{"role": "user", "content": user_text[:3000]}]
        return Reply(
            self.runtime.chat(
                profile,
                compact,
                max_tokens=max_tokens,
                timeout=timeout,
                status=status,
            ),
            used_model=True,
        )
