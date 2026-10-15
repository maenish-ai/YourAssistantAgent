from __future__ import annotations

import re


def classify_share_result_text(text: str) -> str:
    """Classify Facebook feedback after a Share/Post action.

    Returns one of:
      - pending_approval: Facebook accepted the post for admin/moderator review.
      - published: Facebook explicitly reported that it was posted/shared.
      - submitted: the action was accepted but exact visibility was not exposed.

    All three are successful submission states for duplicate-prevention purposes.
    """
    value = re.sub(r"\s+", " ", text or " ").strip().casefold()
    pending_patterns = (
        r"pending (?:admin )?approval",
        r"awaiting (?:admin )?approval",
        r"submitted (?:for|to) (?:admin )?(?:approval|review)",
        r"post is pending",
        r"pending post",
        r"بانتظار موافق",
        r"في انتظار موافق",
        r"بإنتظار موافق",
        r"بانتظار مراجعة",
        r"في انتظار مراجعة",
        r"تم إرسال.*(?:للمراجعة|للموافقة)",
        r"يحتاج.*موافق.*(?:المشرف|الأدمن|الادمن)",
        r"موافقة (?:مسؤول|مشرف|أدمن|ادمن).*مطلوبة",
    )
    if any(re.search(pat, value, re.I) for pat in pending_patterns):
        return "pending_approval"
    published_patterns = (
        r"your post was (?:shared|published|posted)",
        r"shared to .+",
        r"post published",
        r"تمت مشاركة",
        r"تم نشر",
        r"تمت الإضافة إلى المجموعة",
    )
    if any(re.search(pat, value, re.I) for pat in published_patterns):
        return "published"
    return "submitted"
