from __future__ import annotations

import re
import unicodedata

_ARABIC_DIACRITICS = re.compile(r"[\u0610-\u061A\u064B-\u065F\u0670\u06D6-\u06ED]")
_TATWEEL = "\u0640"


def normalize_search(value: str) -> str:
    """Unicode-aware search normalization for Arabic and English.

    It preserves stored text as-is and only normalizes a comparison copy.
    """
    text = unicodedata.normalize("NFKC", value or "")
    text = _ARABIC_DIACRITICS.sub("", text).replace(_TATWEEL, "")
    text = text.translate(str.maketrans({
        "أ": "ا", "إ": "ا", "آ": "ا", "ٱ": "ا",
        "ى": "ي",
        "ؤ": "و",
        "ئ": "ي",
    }))
    text = " ".join(text.split())
    return text.casefold()


def contains_normalized(haystack: str, needle: str) -> bool:
    if not needle:
        return True
    return normalize_search(needle) in normalize_search(haystack)


def normalize_phone(phone: str) -> str:
    digits = re.sub(r"\D+", "", phone or "")
    return digits


def is_valid_international_phone(phone: str) -> bool:
    digits = normalize_phone(phone)
    return 8 <= len(digits) <= 15 and not digits.startswith("0")
