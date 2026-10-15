from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class AgentProfile:
    key: str
    title: str
    subtitle: str
    model_filename: str
    system_prompt: str


HAMMER = AgentProfile(
    key="hammer",
    title="Hammer 2.1 Smart Agent",
    subtitle="0.5B local action model — the only AI brain",
    model_filename="hammer2.1-0.5b-Q4_K_M.gguf",
    system_prompt=(
        "You are the single AI brain inside Your Assistant Agent. The desktop application is your interface, state store, "
        "permission boundary, and tool host. You handle ALL user conversation, including greetings and casual chat, as well "
        "as deciding when an application tool is needed. Reply in the user's language unless a per-user language preference "
        "is supplied in context. Understand colloquial Arabic, especially Jordanian Arabic, but do not invent tool results. "
        "Never claim Facebook, Telegram, GitHub, Google Drive, file, browser, scheduling, or external actions succeeded unless "
        "the application tool result confirms it. For publishing, sending, deleting, security changes, payments, or other "
        "sensitive external actions, respect the application's approval gate. Use the respond function for ordinary conversation. "
        "Be concise, natural, and helpful."
    ),
)

# Old session/profile names still resolve to Hammer so upgrades do not break.
ARABIC = AgentProfile("arabic", HAMMER.title, HAMMER.subtitle, HAMMER.model_filename, HAMMER.system_prompt)
GENERAL = AgentProfile("general", HAMMER.title, HAMMER.subtitle, HAMMER.model_filename, HAMMER.system_prompt)
PROFILES = {"hammer": HAMMER, "arabic": ARABIC, "general": GENERAL, "auto": HAMMER}


def get_profile(key: str | None = None) -> AgentProfile:
    return PROFILES.get((key or "hammer").lower(), HAMMER)
