from __future__ import annotations

import json
import re
from dataclasses import asdict, dataclass, field
from datetime import datetime, timedelta
from typing import Iterable


_ARABIC_DIGITS = str.maketrans("٠١٢٣٤٥٦٧٨٩۰۱۲۳۴۵۶۷۸۹", "01234567890123456789")

DAY_ALIASES = {
    0: ("الاثنين", "الإثنين", "اثنين", "monday", "mon"),
    1: ("الثلاثاء", "ثلاثاء", "tuesday", "tue", "tues"),
    2: ("الأربعاء", "الاربعاء", "أربعاء", "اربعاء", "wednesday", "wed"),
    3: ("الخميس", "خميس", "thursday", "thu", "thur", "thurs"),
    4: ("الجمعة", "جمعه", "جمعة", "friday", "fri"),
    5: ("السبت", "سبت", "saturday", "sat"),
    6: ("الأحد", "الاحد", "أحد", "احد", "sunday", "sun"),
}

DAY_NAMES_AR = ["الاثنين", "الثلاثاء", "الأربعاء", "الخميس", "الجمعة", "السبت", "الأحد"]
DAY_NAMES_EN = ["Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday", "Sunday"]


@dataclass
class SmartPlan:
    name: str
    command_text: str
    source_page_url: str
    weekdays: list[int] = field(default_factory=list)  # [] means every day
    run_time: str = "20:00"
    post_mode: str = "fixed"  # fixed | rotation
    post_offset: int = 0
    group_keyword: str = ""
    max_groups: int = 100
    interval_seconds: int = 60
    no_repeat_days: int = 14
    share_mode: str = "native_share"

    def to_dict(self) -> dict:
        return asdict(self)

    def to_json(self) -> str:
        return json.dumps(self.to_dict(), ensure_ascii=False)

    def summary(self, language: str = "ar") -> str:
        ar = language == "ar"
        if self.weekdays:
            names = DAY_NAMES_AR if ar else DAY_NAMES_EN
            days = "، ".join(names[d] for d in self.weekdays)
        else:
            days = "كل يوم" if ar else "Every day"

        if self.post_mode == "rotation":
            post = "تدوير البوستات تلقائيًا" if ar else "Rotate posts automatically"
        elif self.post_offset == 0:
            post = "آخر بوست" if ar else "Latest post"
        else:
            post = (f"البوست السابق رقم {self.post_offset}" if ar else f"Previous post offset {self.post_offset}")

        keyword = self.group_keyword or ("كل الجروبات المحفوظة" if ar else "all saved groups")
        if ar:
            return (
                f"المصدر: {self.source_page_url}\n"
                f"الموعد: {days} الساعة {self.run_time}\n"
                f"البوست: {post}\n"
                f"الجروبات: الاسم/الوسم يحتوي «{keyword}»\n"
                f"الحد الأقصى: {self.max_groups} — الفاصل: {self.interval_seconds} ثانية\n"
                f"منع التكرار: {self.no_repeat_days} يوم — طريقة المشاركة: مشاركة أصلية"
            )
        return (
            f"Source: {self.source_page_url}\n"
            f"Schedule: {days} at {self.run_time}\n"
            f"Post: {post}\n"
            f"Groups: name/tag contains '{keyword}'\n"
            f"Maximum: {self.max_groups} — interval: {self.interval_seconds}s\n"
            f"No-repeat window: {self.no_repeat_days} days — share mode: native share"
        )


class SmartPlannerError(ValueError):
    pass


class SmartPlanner:
    """Deterministic natural-language planner for common Arabic/English campaign instructions.

    It intentionally does not call an external AI service. The generated plan is always shown
    for approval before it becomes an active rule.
    """

    def __init__(self, language: str = "ar"):
        self.language = language if language in {"ar", "en"} else "ar"

    @staticmethod
    def normalize(text: str) -> str:
        text = (text or "").translate(_ARABIC_DIGITS)
        text = re.sub(r"[\u064B-\u065F\u0670]", "", text)
        text = text.replace("ـ", "")
        return re.sub(r"\s+", " ", text).strip()

    @staticmethod
    def _extract_url(text: str) -> str:
        m = re.search(r"https?://(?:www\.)?facebook\.com/[^\s،,]+", text, re.I)
        return (m.group(0).rstrip(".؛;،,") if m else "")

    def _parse_weekdays(self, text: str) -> list[int]:
        t = text.casefold()
        result = []
        for day, aliases in DAY_ALIASES.items():
            if any(alias.casefold() in t for alias in aliases):
                result.append(day)
        if result:
            return sorted(set(result))
        if re.search(r"\b(every day|daily)\b", t) or "كل يوم" in t or "يوميا" in t or "يوميًا" in t:
            return []
        return []

    @staticmethod
    def _parse_time(text: str, default: str = "20:00") -> str:
        # Arabic/English explicit clock time. 8 مساءً => 20:00.
        patterns = [
            r"(?:الساعة|ساعه|عند|at)\s*(\d{1,2})(?::(\d{1,2}))?\s*(صباحا|صباحًا|صباح|مساء|مساءً|pm|am)?",
            r"\b(\d{1,2}):(\d{2})\s*(pm|am)?\b",
        ]
        for pat in patterns:
            m = re.search(pat, text, re.I)
            if not m:
                continue
            hour = int(m.group(1))
            minute = int(m.group(2) or 0)
            suffix = (m.group(3) or "").casefold()
            if hour > 23 or minute > 59:
                continue
            if suffix in {"مساء", "مساءً", "pm"} and hour < 12:
                hour += 12
            elif suffix in {"صباح", "صباحا", "صباحًا", "am"} and hour == 12:
                hour = 0
            return f"{hour:02d}:{minute:02d}"
        return default

    @staticmethod
    def _parse_interval(text: str, default: int = 60) -> int:
        if re.search(r"كل\s*(?:نص|نصف)\s*(?:دقيقة|دقيقه)", text, re.I):
            return 30
        m = re.search(r"(?:كل|فاصل(?:\s+زمني)?(?:\s+بين.*)?|every)\s*(\d+)\s*(ثانية|ثانيه|ثوان|ثواني|دقيقة|دقيقه|دقائق|seconds?|secs?|minutes?|mins?)", text, re.I)
        if not m:
            return max(30, default)
        value = int(m.group(1))
        unit = m.group(2).casefold()
        if "دقيق" in unit or "min" in unit:
            value *= 60
        return max(30, min(value, 6 * 3600))

    @staticmethod
    def _parse_max_groups(text: str, default: int = 100) -> int:
        m = re.search(r"(?:اول|أول|first|حد(?:\s+اقصى|\s+أقصى)?|maximum|max)\s*(\d+)\s*(?:جروب|جروبات|مجموعة|مجموعات|groups?)", text, re.I)
        if m:
            return max(1, min(int(m.group(1)), 500))
        return max(1, min(default, 500))

    @staticmethod
    def _parse_no_repeat_days(text: str, default: int = 14) -> int:
        m = re.search(r"(?:لا\s*تكرر|منع\s*التكرار|no\s*repeat).*?(\d+)\s*(?:يوم|ايام|أيام|days?)", text, re.I)
        if m:
            return max(0, min(int(m.group(1)), 3650))
        return max(0, default)

    @staticmethod
    def _parse_post(text: str) -> tuple[str, int]:
        t = text.casefold()
        if any(x in t for x in ("تدوير", "دور على", "يرجع من الاول", "يرجع من الأول", "rotation", "rotate posts", "cycle posts")):
            return "rotation", 0
        # Explicit numeric offset has priority.
        m = re.search(r"(?:post\s*offset|ترتيب\s*البوست|البوست\s*رقم)\s*(\d+)", t)
        if m:
            return "fixed", max(0, int(m.group(1)))
        if any(x in t for x in ("قبل السابق", "قبل اللي قبله", "two posts ago", "2 posts ago")):
            return "fixed", 2
        if any(x in t for x in ("البوست السابق", "البوست اللي قبله", "البوست الي قبله", "اللي قبليها", "اللي قبليه", "previous post", "one post ago")):
            return "fixed", 1
        return "fixed", 0

    @staticmethod
    def _clean_keyword(value: str) -> str:
        value = re.split(r"(?:\s+(?:و?كل|يوم|الساعة|ساعه|عند|وبعدين|ثم|مع\s+فاصل|every|at)\b|[،,.;؛])", value, maxsplit=1, flags=re.I)[0]
        value = value.strip(" \t\n\r'\"«»")
        return value[:120]

    def _parse_group_keyword(self, text: str) -> str:
        quoted = re.search(r"(?:جروبات|مجموعات|groups?).*?[«\"']([^»\"']+)[»\"']", text, re.I)
        if quoted:
            return self._clean_keyword(quoted.group(1))
        patterns = [
            r"(?:تحتوي\s+(?:اسمها\s+)?على|اسمها\s+فيه|اسمها\s+يحتوي|فيها(?:\s+كلمة)?|باسم|وسم)\s+([^،,.;؛]+)",
            r"(?:groups?\s+(?:containing|with)|group\s+name\s+contains)\s+([^,.;]+)",
        ]
        for pat in patterns:
            m = re.search(pat, text, re.I)
            if m:
                return self._clean_keyword(m.group(1))
        return ""

    def parse_many(
        self,
        command: str,
        default_source_page: str = "",
        default_interval: int = 60,
        default_max_groups: int = 100,
        default_no_repeat_days: int = 14,
    ) -> list[SmartPlan]:
        """Parse one instruction or several weekday clauses into separate rules.

        Example: "Monday ... Fuheis. Tuesday ... Dabouq" becomes two independent
        rules so each day can use a different time, post and group keyword.
        """
        raw = (command or "").strip()
        if not raw:
            raise SmartPlannerError("اكتب أمرًا للحملة أولًا." if self.language == "ar" else "Enter a campaign instruction first.")
        text = self.normalize(raw)
        whole_source = self._extract_url(text) or (default_source_page or "").strip()
        aliases = sorted({a for vals in DAY_ALIASES.values() for a in vals}, key=len, reverse=True)
        pattern = re.compile(r"(?<!\w)(?:يوم\s+)?(?:" + "|".join(re.escape(a) for a in aliases) + r")(?!\w)", re.I)
        matches = list(pattern.finditer(text))
        if len(matches) < 2:
            return [self.parse(text, whole_source, default_interval, default_max_groups, default_no_repeat_days)]

        plans: list[SmartPlan] = []
        for i, m in enumerate(matches):
            start = m.start()
            end = matches[i + 1].start() if i + 1 < len(matches) else len(text)
            segment = text[start:end].strip(" .،,؛;\n\t")
            if not segment:
                continue
            plans.append(self.parse(segment, whole_source, default_interval, default_max_groups, default_no_repeat_days))
        return plans or [self.parse(text, whole_source, default_interval, default_max_groups, default_no_repeat_days)]

    def parse(
        self,
        command: str,
        default_source_page: str = "",
        default_interval: int = 60,
        default_max_groups: int = 100,
        default_no_repeat_days: int = 14,
        name: str = "",
    ) -> SmartPlan:
        raw = (command or "").strip()
        if not raw:
            raise SmartPlannerError("اكتب أمرًا للحملة أولًا." if self.language == "ar" else "Enter a campaign instruction first.")
        text = self.normalize(raw)
        source = self._extract_url(text) or (default_source_page or "").strip()
        if not source:
            raise SmartPlannerError(
                "حدد رابط صفحة المصدر مرة واحدة قبل اعتماد الأمر." if self.language == "ar"
                else "Set the source Facebook page URL before approving this instruction."
            )
        mode, offset = self._parse_post(text)
        weekdays = self._parse_weekdays(text)
        run_time = self._parse_time(text)
        keyword = self._parse_group_keyword(text)
        interval = self._parse_interval(text, default_interval)
        max_groups = self._parse_max_groups(text, default_max_groups)
        no_repeat = self._parse_no_repeat_days(text, default_no_repeat_days)
        rule_name = name.strip() if name else self._suggest_name(weekdays, keyword, run_time)
        return SmartPlan(
            name=rule_name,
            command_text=raw,
            source_page_url=source,
            weekdays=weekdays,
            run_time=run_time,
            post_mode=mode,
            post_offset=offset,
            group_keyword=keyword,
            max_groups=max_groups,
            interval_seconds=interval,
            no_repeat_days=no_repeat,
            share_mode="native_share",
        )

    def _suggest_name(self, weekdays: Iterable[int], keyword: str, run_time: str) -> str:
        days = list(weekdays)
        if self.language == "ar":
            day_text = "يومي" if not days else "+".join(DAY_NAMES_AR[d] for d in days)
            return f"ذكي - {keyword or 'كل الجروبات'} - {day_text} {run_time}"[:160]
        day_text = "Daily" if not days else "+".join(DAY_NAMES_EN[d] for d in days)
        return f"Smart - {keyword or 'All groups'} - {day_text} {run_time}"[:160]


def calculate_next_run(weekdays: Iterable[int], run_time: str, now: datetime | None = None) -> str:
    now = now or datetime.now()
    try:
        hour, minute = [int(x) for x in run_time.split(":", 1)]
    except Exception as exc:
        raise ValueError(f"Invalid run_time: {run_time}") from exc
    target_days = sorted(set(int(d) for d in weekdays if 0 <= int(d) <= 6))
    for delta in range(0, 8):
        day = now + timedelta(days=delta)
        if target_days and day.weekday() not in target_days:
            continue
        candidate = day.replace(hour=hour, minute=minute, second=0, microsecond=0)
        if candidate > now:
            return candidate.isoformat()
    # Defensive fallback; normal weekly/daily schedules are found above.
    return (now + timedelta(days=1)).replace(hour=hour, minute=minute, second=0, microsecond=0).isoformat()
