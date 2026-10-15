from __future__ import annotations


def ui_text(ar: str, en: str, language: str = "ar") -> str:
    """Return exactly one language. v2 never mixes Arabic/English in runtime UI."""
    return en if language == "en" else ar


def is_rtl(language: str) -> bool:
    return language != "en"


def anchor_for(language: str) -> str:
    return "e" if is_rtl(language) else "w"
