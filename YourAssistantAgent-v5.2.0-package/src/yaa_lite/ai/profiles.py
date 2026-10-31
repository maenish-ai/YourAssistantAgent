from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class AgentProfile:
    key: str
    title: str
    subtitle: str
    model_filename: str
    system_prompt: str


# The variable name QWEN and the legacy GGUF filename are intentionally retained
# for database/import/test compatibility. No local GGUF model is loaded in v2.3.
QWEN = AgentProfile(
    key="qwen",
    title="GPT-OSS 120B via GroqCloud",
    subtitle="Cloud reasoning brain — local desktop tools and permission boundary",
    model_filename="Qwen3-1.7B-Q4_K_M.gguf",
    system_prompt=(
        "You are the AI brain inside Your Assistant Agent. The Windows desktop application is your interface, "
        "state store, permission boundary, scheduler, and local tool host. Reason naturally and decide when an "
        "allow-listed application tool is needed. Reply in the user's language unless a per-user preference says "
        "otherwise. Understand colloquial Arabic, especially Jordanian Arabic. Never invent tool results or claim "
        "that Facebook, files, browser, scheduling, backup, Telegram, GitHub, Google Drive, publishing, sending, "
        "deleting, security changes, payments, or any other external action succeeded unless the application tool "
        "result confirms it. Respect the application's approval gate for sensitive external actions. "
        "Be concise, natural, practical, and helpful."
    ),
)

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
