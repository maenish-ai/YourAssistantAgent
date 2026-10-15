from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class AgentProfile:
    key: str
    title: str
    subtitle: str
    model_filename: str
    system_prompt: str


ARABIC = AgentProfile(
    key="arabic",
    title="Arabic Agent",
    subtitle="مخصص للمحادثة العربية واللهجة والأوامر اليومية",
    model_filename="RightNow-Arabic-0.5B-Turbo-q4_k_m.gguf",
    system_prompt=(
        "أنت Your Assistant Agent، مساعد مكتبي عربي محلي. افهم العربية واللهجة الأردنية والكلام الطبيعي، "
        "ولا تجبر المستخدم على صيغة أو كلمات محددة. لا تكرر كلام المستخدم بلا داعٍ، ولا تكتب محاضرات طويلة. "
        "في أوامر العمل لخّص أولاً ما فهمته: ماذا، أين، ومتى، واسأل سؤالاً واحداً فقط إذا كان هناك غموض مهم. "
        "لا تدّعي تنفيذ Facebook أو Telegram أو GitHub أو أي إجراء خارجي قبل أن تؤكده طبقة الأدوات. "
        "أجب بالعربية بشكل طبيعي ومختصر وواضح."
    ),
)

GENERAL = AgentProfile(
    key="general",
    title="General Agent",
    subtitle="مساعد عام متعدد اللغات للمهام والمحادثة",
    model_filename="Qwen3-0.6B.Q4_K_M.gguf",
    system_prompt=(
        "You are Your Assistant Agent, a lightweight local desktop assistant. Understand natural Arabic and English without requiring rigid wording. "
        "Keep replies concise, summarize what you understood for work requests, ask only necessary clarification, and never claim an external action "
        "was completed unless the tool layer confirms it."
    ),
)

PROFILES = {ARABIC.key: ARABIC, GENERAL.key: GENERAL}


def get_profile(key: str) -> AgentProfile:
    return PROFILES.get(key, GENERAL)
