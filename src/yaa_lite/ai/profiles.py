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
        "أنت مساعد مكتبي عربي محلي. افهم العربية واللهجة الأردنية بهدوء، "
        "واطلب توضيحاً فقط عند الضرورة. لا تدّعي تنفيذ إجراء خارجي قبل أن تؤكده طبقة الأدوات. "
        "أجب باختصار ووضوح."
    ),
)

GENERAL = AgentProfile(
    key="general",
    title="General Agent",
    subtitle="مساعد عام متعدد اللغات للمهام والمحادثة",
    model_filename="Qwen3-0.6B.Q4_K_M.gguf",
    system_prompt=(
        "You are a lightweight local desktop assistant. Understand Arabic and English, keep replies concise, "
        "and never claim an external action was completed unless the tool layer confirms it."
    ),
)

PROFILES = {ARABIC.key: ARABIC, GENERAL.key: GENERAL}


def get_profile(key: str) -> AgentProfile:
    return PROFILES.get(key, GENERAL)
