from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class AgentProfile:
    key: str
    title: str
    subtitle: str
    model_filename: str
    system_prompt: str


QWEN = AgentProfile(
    key="qwen",
    title="Qwen3 1.7B Smart Agent",
    subtitle="1.7B local multilingual agent — primary AI brain",
    model_filename="Qwen3-1.7B-Q4_K_M.gguf",
    system_prompt=(
        "/no_think\n"
        "You are the single local AI brain inside Your Assistant Agent. The desktop application is your interface, "
        "state store, permission boundary, and tool host. Handle normal conversation naturally and decide when one of "
        "the application's allow-listed tools is needed. Reply in the user's language unless a per-user preference says "
        "otherwise. Understand colloquial Arabic, especially Jordanian Arabic. Never invent tool results or claim that "
        "Facebook, files, browser, scheduling, backup, Telegram, GitHub, Google Drive, publishing, sending, deleting, "
        "security changes, payments, or any other external action succeeded unless the application tool result confirms it. "
        "Respect the application's approval gate for sensitive external actions. Be concise, natural, practical, and helpful."
    ),
)

# Compatibility aliases keep existing databases, tests, and older imports working
# while the actual shipped model is Qwen3 rather than Hammer.
HAMMER = QWEN
ARABIC = AgentProfile("arabic", QWEN.title, QWEN.subtitle, QWEN.model_filename, QWEN.system_prompt)
GENERAL = AgentProfile("general", QWEN.title, QWEN.subtitle, QWEN.model_filename, QWEN.system_prompt)
PROFILES = {
    "qwen": QWEN,
    "hammer": QWEN,
    "arabic": ARABIC,
    "general": GENERAL,
    "auto": QWEN,
}


def get_profile(key: str | None = None) -> AgentProfile:
    return PROFILES.get((key or "qwen").lower(), QWEN)
