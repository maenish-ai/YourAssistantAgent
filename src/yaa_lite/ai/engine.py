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
    "انت مين": "أنا Your Assistant Agent، مساعدك المحلي. عندي Hammer 2.1 للمهام والأدوات، واحكي معي طبيعي.",
    "مين انت": "أنا Your Assistant Agent، مساعدك المحلي. عندي Hammer 2.1 للمهام والأدوات، واحكي معي طبيعي.",
}
_FAST_EN = {
    "hi": "Hi! What would you like to do?",
    "hello": "Hello! What would you like to do?",
    "how are you": "I'm ready. What would you like me to do?",
    "what's up": "I'm ready. What would you like to work on?",
    "who are you": "I'm Your Assistant Agent. Hammer 2.1 handles local tool routing and tasks, and you can talk to me naturally.",
}


def quick_reply(user_text: str) -> str | None:
    normalized = _normalize(user_text)
    return _FAST_AR.get(normalized) or _FAST_EN.get(normalized)


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
        instant = quick_reply(user_text)
        if instant:
            return Reply(instant, used_model=False)

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
