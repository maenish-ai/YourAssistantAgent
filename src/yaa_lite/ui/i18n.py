from __future__ import annotations


def ui_text(ar: str, en: str, language: str = "bilingual") -> str:
    if language == "ar":
        return ar
    if language == "en":
        return en
    return f"{ar} / {en}"
