from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class AgentProfile:
    key: str
    title: str
    subtitle: str
    model_filename: str
    system_prompt: str


# v1.7 uses a single local model for both conversation and agentic tool routing.
# Arabic/General aliases are kept only so conversations created by older builds
# continue to open without migration errors.
HAMMER = AgentProfile(
    key="hammer",
    title="Hammer 2.1 Smart Agent",
    subtitle="0.5B local action model for conversation + tool calling",
    model_filename="hammer2.1-0.5b-Q4_K_M.gguf",
    system_prompt=(
        "You are Your Assistant Agent, a private local desktop assistant. Reply in the same language as the user "
        "(Arabic or English) and keep ordinary conversation natural and concise. You are also a tool-using smart agent. "
        "When tools are provided, choose a tool only when it is relevant. Never claim that Facebook, Telegram, GitHub, "
        "scheduling, or any external action succeeded unless the tool layer confirms it. For actions that publish, send, "
        "delete, or change external data, prefer preparing a plan and waiting for user confirmation. Understand colloquial "
        "Arabic, including Jordanian phrasing, without requiring rigid keywords."
    ),
)

# Backward-compatibility aliases: all point to the same Hammer GGUF.
ARABIC = AgentProfile(
    key="arabic",
    title="Smart Agent",
    subtitle="Auto Arabic/English conversation",
    model_filename=HAMMER.model_filename,
    system_prompt=HAMMER.system_prompt,
)
GENERAL = AgentProfile(
    key="general",
    title="Smart Agent",
    subtitle="Auto Arabic/English conversation",
    model_filename=HAMMER.model_filename,
    system_prompt=HAMMER.system_prompt,
)

PROFILES = {"hammer": HAMMER, "arabic": ARABIC, "general": GENERAL, "auto": HAMMER}


def get_profile(key: str | None = None) -> AgentProfile:
    # New UI exposes a single assistant. Old session keys still map to Hammer.
    return PROFILES.get((key or "hammer").lower(), HAMMER)
