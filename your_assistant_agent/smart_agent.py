from __future__ import annotations

import json
import re
from dataclasses import asdict, dataclass, field
from datetime import datetime, timedelta
from typing import Iterable, Mapping, Any


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

_AR_HOUR_WORDS = {
    "الحادية عشرة": 11,
    "الحادي عشر": 11,
    "الثانية عشرة": 12,
    "الثاني عشر": 12,
    "الواحدة": 1,
    "الاولى": 1,
    "الأولى": 1,
    "الثانية": 2,
    "الثالثة": 3,
    "الرابعة": 4,
    "الخامسة": 5,
    "السادسة": 6,
    "السابعة": 7,
    "الثامنة": 8,
    "التاسعة": 9,
    "العاشرة": 10,
}

_GROUP_WORDS_RE = re.compile(r"(?:جروبات|الجروبات|مجموعات|المجموعات|groups?)", re.I)
_FOLLOWUP_RE = re.compile(
    r"(?:خليها|خلّيها|خليه|خلّيه|غيرها|غيّرها|غيره|غيّره|عدلها|عدّلها|عدل|عدّل|"
    r"بدل|بدال|نفسها|نفسه|نفس القاعدة|خلي الوقت|غير الوقت|change\s+it|instead|same\s+rule)",
    re.I,
)


@dataclass
class SmartPlan:
    name: str
    command_text: str
    source_page_url: str
    weekdays: list[int] = field(default_factory=list)  # [] means every day
    run_time: str = "20:00"
    run_once_at: str = ""  # ISO local datetime for one-time instructions
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
        if self.run_once_at:
            try:
                once = datetime.fromisoformat(self.run_once_at)
                days = once.strftime("%Y-%m-%d")
            except Exception:
                days = self.run_once_at
        elif self.weekdays:
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

        if ar:
            groups = (
                f"الاسم/الوسم يحتوي «{self.group_keyword}»"
                if self.group_keyword else "كل الجروبات المحفوظة"
            )
            return (
                f"المصدر: {self.source_page_url}\n"
                f"الموعد: {'مرة واحدة ' if self.run_once_at else ''}{days} الساعة {self.run_time}\n"
                f"البوست: {post}\n"
                f"الجروبات: {groups}\n"
                f"الحد الأقصى للتنفيذ: {self.max_groups} — الفاصل: {self.interval_seconds} ثانية\n"
                f"منع التكرار: {self.no_repeat_days} يوم — طريقة المشاركة: مشاركة أصلية\n"
                f"موافقة الأدمن: إذا استلم Facebook المنشور للمراجعة تُسجل Pending Approval وليست Failed ولا يعاد إرسالها"
            )
        groups = f"name/tag contains '{self.group_keyword}'" if self.group_keyword else "all saved groups"
        return (
            f"Source: {self.source_page_url}\n"
            f"Schedule: {'Once ' if self.run_once_at else ''}{days} at {self.run_time}\n"
            f"Post: {post}\n"
            f"Groups: {groups}\n"
            f"Execution maximum: {self.max_groups} — interval: {self.interval_seconds}s\n"
            f"No-repeat window: {self.no_repeat_days} days — share mode: native share\n"
            f"Admin approval: a post accepted for review is Pending Approval, not Failed, and is not re-sent"
        )


class SmartPlannerError(ValueError):
    pass


class SmartPlanner:
    """Natural-language planner for Arabic/English Facebook sharing instructions.

    v0.9 strengthens the parser around intent/entity extraction and, most
    importantly, fails safely when a group filter is implied but not understood.
    It also supports short follow-up edits against a preview context, e.g.
    "خليها الساعة 9 بدل 8".
    """

    def __init__(self, language: str = "ar"):
        self.language = language if language in {"ar", "en"} else "ar"

    @staticmethod
    def normalize(text: str) -> str:
        text = (text or "").translate(_ARABIC_DIGITS)
        text = re.sub(r"[\u064B-\u065F\u0670]", "", text)
        text = text.replace("ـ", "")
        return re.sub(r"\s+", " ", text).strip()

    @classmethod
    def is_followup(cls, text: str) -> bool:
        return bool(_FOLLOWUP_RE.search(cls.normalize(text)))

    @staticmethod
    def _extract_url(text: str) -> str:
        m = re.search(r"https?://(?:www\.)?facebook\.com/[^\s،,]+", text, re.I)
        return (m.group(0).rstrip(".؛;،,") if m else "")

    @staticmethod
    def _contains_any(text: str, values: Iterable[str]) -> bool:
        t = text.casefold()
        return any(v.casefold() in t for v in values)

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
        # Arabic/English explicit numeric clock time. 8 مساءً => 20:00.
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

        # Written Arabic hour names: "الساعة الثامنة مساء" and simple
        # quarter/half variants. Longest phrases are checked first.
        for phrase, base_hour in sorted(_AR_HOUR_WORDS.items(), key=lambda kv: len(kv[0]), reverse=True):
            m = re.search(
                rf"(?:الساعة|ساعه|عند)\s*{re.escape(phrase)}\s*"
                rf"(?P<minute>والنصف|و\s*النصف|والربع|و\s*الربع|الا\s*ربع|إلا\s*ربع)?\s*"
                rf"(?P<suffix>صباحا|صباحًا|صباح|مساء|مساءً)?",
                text,
                re.I,
            )
            if not m:
                continue
            hour = base_hour
            minute_token = (m.group("minute") or "").replace(" ", "")
            if "النصف" in minute_token:
                minute = 30
            elif "الربع" in minute_token and ("الا" in minute_token or "إلا" in minute_token):
                hour = 12 if hour == 1 else hour - 1
                minute = 45
            elif "الربع" in minute_token:
                minute = 15
            else:
                minute = 0
            suffix = (m.group("suffix") or "").casefold()
            if suffix in {"مساء", "مساءً"} and hour < 12:
                hour += 12
            elif suffix in {"صباح", "صباحا", "صباحًا"} and hour == 12:
                hour = 0
            return f"{hour:02d}:{minute:02d}"
        return default

    @staticmethod
    def _has_explicit_time(text: str) -> bool:
        return bool(
            re.search(r"(?:الساعة|ساعه|عند|\bat\b)\s*(?:\d|الواحدة|الاولى|الأولى|الثانية|الثالثة|الرابعة|الخامسة|السادسة|السابعة|الثامنة|التاسعة|العاشرة|الحادية|الحادي)", text, re.I)
            or re.search(r"\b\d{1,2}:\d{2}\b", text)
        )

    @staticmethod
    def _has_date_cue(text: str) -> bool:
        return bool(re.search(r"(?:^|\s)(?:اليوم|غدا|غداً|بكره|بكرة|بكرا|بعد\s+غد|بعد\s+بكرا|today|tomorrow)(?:\s|$)", text, re.I)) or bool(
            re.search(r"\b(?:20\d{2}-\d{1,2}-\d{1,2}|\d{1,2}/\d{1,2}/20\d{2})\b", text)
        )

    @staticmethod
    def _parse_once_at(text: str, run_time: str) -> str:
        t = text.casefold()
        target_date = None
        offset = None
        if re.search(r"(?:^|\s)(?:بعد\s+غد|بعد\s+بكرا|day\s+after\s+tomorrow)(?:\s|$)", t):
            offset = 2
        elif re.search(r"(?:^|\s)(?:اليوم|today)(?:\s|$)", t):
            offset = 0
        elif re.search(r"(?:^|\s)(?:غدا|غداً|بكره|بكرة|بكرا|tomorrow)(?:\s|$)", t):
            offset = 1

        iso = re.search(r"\b(20\d{2})-(\d{1,2})-(\d{1,2})\b", t)
        slash = re.search(r"\b(\d{1,2})/(\d{1,2})/(20\d{2})\b", t)
        try:
            if iso:
                target_date = datetime(int(iso.group(1)), int(iso.group(2)), int(iso.group(3)))
            elif slash:
                target_date = datetime(int(slash.group(3)), int(slash.group(2)), int(slash.group(1)))
        except ValueError as exc:
            raise SmartPlannerError("التاريخ المحدد غير صحيح." if re.search(r"[\u0600-\u06ff]", text) else "The requested date is invalid.") from exc

        if target_date is None and offset is None:
            return ""
        hour, minute = [int(x) for x in run_time.split(":", 1)]
        target = target_date or (datetime.now() + timedelta(days=int(offset or 0)))
        target = target.replace(hour=hour, minute=minute, second=0, microsecond=0)
        if target <= datetime.now():
            raise SmartPlannerError(
                "الموعد المحدد مضى بالفعل." if re.search(r"[\u0600-\u06ff]", text) else "The requested time has already passed."
            )
        return target.isoformat()

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
    def _has_interval_cue(text: str) -> bool:
        return bool(re.search(r"(?:كل\s*(?:نص|نصف|\d+)\s*(?:دقيقة|دقيقه|ثانية|ثانيه)|فاصل|every\s+\d+)", text, re.I))

    @staticmethod
    def _parse_max_groups(text: str, default: int = 100) -> int:
        m = re.search(r"(?:اول|أول|first|حد(?:\s+اقصى|\s+أقصى)?|maximum|max)\s*(\d+)\s*(?:جروب|جروبات|مجموعة|مجموعات|groups?)", text, re.I)
        if m:
            return max(1, min(int(m.group(1)), 500))
        return max(1, min(default, 500))

    @staticmethod
    def _has_max_groups_cue(text: str) -> bool:
        return bool(re.search(r"(?:اول|أول|first|حد(?:\s+اقصى|\s+أقصى)?|maximum|max)\s*\d+", text, re.I))

    @staticmethod
    def _parse_no_repeat_days(text: str, default: int = 14) -> int:
        m = re.search(r"(?:لا\s*تكرر|منع\s*التكرار|no\s*repeat).*?(\d+)\s*(?:يوم|ايام|أيام|days?)", text, re.I)
        if m:
            return max(0, min(int(m.group(1)), 3650))
        return max(0, default)

    @staticmethod
    def _has_no_repeat_cue(text: str) -> bool:
        return bool(re.search(r"(?:لا\s*تكرر|منع\s*التكرار|no\s*repeat)", text, re.I))

    @staticmethod
    def _parse_post(text: str) -> tuple[str, int]:
        t = text.casefold()
        if any(x in t for x in ("تدوير", "دور على", "يرجع من الاول", "يرجع من الأول", "rotation", "rotate posts", "cycle posts")):
            return "rotation", 0
        m = re.search(r"(?:post\s*offset|ترتيب\s*البوست|البوست\s*رقم)\s*(\d+)", t)
        if m:
            return "fixed", max(0, int(m.group(1)))
        if any(x in t for x in ("قبل السابق", "قبل اللي قبله", "two posts ago", "2 posts ago")):
            return "fixed", 2
        if any(x in t for x in ("البوست السابق", "المنشور السابق", "الإعلان السابق", "الاعلان السابق", "البوست اللي قبله", "البوست الي قبله", "previous post", "one post ago")):
            return "fixed", 1
        return "fixed", 0

    @staticmethod
    def _has_post_cue(text: str) -> bool:
        return bool(re.search(r"(?:بوست|منشور|اعلان|إعلان|post|rotation|تدوير)", text, re.I))

    @staticmethod
    def _clean_keyword(value: str) -> str:
        value = SmartPlanner.normalize(value)
        # Stop before scheduling/action clauses. This is the key difference for
        # phrases such as "كلمة خلدة وذلك على الساعة الثامنة مساء".
        value = re.split(
            r"(?:\s+(?:وذلك|وذالك|و\s*ذلك|ثم|وبعدين|بعدها|مع\s+فاصل|بفاصل|بحد\s+(?:اقصى|أقصى)|حد\s+(?:اقصى|أقصى)|"
            r"الساعة|ساعه|عند|اليوم|غدا|غداً|بكرا|بكرة|بكره|every|\bat\b)\b|[،,.;؛])",
            value,
            maxsplit=1,
            flags=re.I,
        )[0]
        value = re.sub(r"^(?:كلمة|كلمه|لفظ|عبارة|عباره|منطقة|منطقه)\s+", "", value, flags=re.I)
        value = value.strip(" \t\n\r'\"«»:-")
        # A captured generic is not a real filter.
        if value.casefold() in {
            "كل", "جميع", "كافة", "الجميع", "الجروبات", "المجموعات", "مجموعات", "جروبات",
            "كلمة", "كلمه", "لفظ", "عبارة", "عباره", "المحفوظة", "المحفوظة عندي",
            "all", "all groups", "groups", "group", "saved", "saved groups",
        }:
            return ""
        return value[:120]

    @staticmethod
    def _mentions_groups(text: str) -> bool:
        return bool(_GROUP_WORDS_RE.search(text))

    @staticmethod
    def _explicit_all_groups(text: str) -> bool:
        return bool(re.search(r"(?:كل|جميع|كافة)\s+(?:ال)?(?:جروبات|مجموعات)\b|\ball\s+(?:saved\s+)?groups\b", text, re.I))

    @staticmethod
    def _has_group_filter_hint(text: str) -> bool:
        return bool(re.search(
            r"(?:اسمها|اسم\s+(?:الجروب|المجموعة)|في\s+اسمها|باسمها|جزء\s+من\s+اسمها|"
            r"يوجد\s+(?:بها|فيها)|موجود\s+(?:بها|فيها)|فيها\s+(?:كلمة|كلمه)?|بها\s+(?:كلمة|كلمه)?|"
            r"تحتوي|يحتوي|كلمة\s+[^\s]+|name\s+(?:contains|has)|groups?\s+(?:containing|with))",
            text,
            re.I,
        ))

    def _parse_group_keyword(self, text: str) -> str:
        # Quoted target near a group reference is the strongest signal.
        quoted = re.search(r"(?:جروبات|مجموعات|groups?).*?[«\"']([^»\"']+)[»\"']", text, re.I)
        if quoted:
            candidate = self._clean_keyword(quoted.group(1))
            if candidate:
                return candidate

        patterns = [
            # "جميع المجموعات التي يوجد بها كلمة خلدة"
            r"(?:جروبات|الجروبات|مجموعات|المجموعات|groups?).{0,90}?(?:التي|اللي|الي)?\s*(?:يوجد|توجد|موجود|موجودة|في)\s*(?:بها|فيها|باسمها|في\s+اسمها)\s*(?:كلمة|كلمه|لفظ|عبارة|عباره)?\s*([^،,.;؛]+)",
            # "المجموعات التي جزء من اسمها يكون صويلح"
            r"(?:جروبات|الجروبات|مجموعات|المجموعات).*?(?:جزء\s+من\s+)?اسمها\s+(?:يكون|هو|فيه|فيها|يحتوي(?:\s+على)?|تحتوي(?:\s+على)?)\s*(?:كلمة|كلمه)?\s*([^،,.;؛]+)",
            # "في اسمها خلدة" / "باسمها خلدة"
            r"(?:في\s+اسمها|باسمها)\s*(?:يوجد|موجود|فيه|يكون|كلمة|كلمه)?\s*([^،,.;؛]+)",
            # Existing common variants.
            r"(?:تحتوي\s+(?:اسمها\s+)?على|اسمها\s+فيه|اسمها\s+يحتوي(?:\s+على)?|فيها(?:\s+(?:كلمة|كلمه))?|بها(?:\s+(?:كلمة|كلمه))?|وسم)\s+([^،,.;؛]+)",
            r"(?:جزء\s+من\s+اسمها)\s+(?:يكون\s+)?([^،,.;؛]+)",
            r"(?:groups?\s+(?:containing|with)|group\s+name\s+(?:contains|has))\s+([^,.;]+)",
            # Natural shorthand: "على جروبات خلدة" / "مجموعات مرج الحمام".
            r"(?:على\s+|الى\s+|إلى\s+)?(?:جروبات|الجروبات|مجموعات|المجموعات)\s+(?!(?:التي|اللي|الي|كل|جميع|كافة)\b)([^،,.;؛]+)",
        ]
        for pat in patterns:
            m = re.search(pat, text, re.I)
            if not m:
                continue
            candidate = self._clean_keyword(m.group(1))
            if candidate:
                return candidate

        # Follow-up shorthand, e.g. "خليها على صويلح بدل خلدة".
        m = re.search(r"(?:خليها|خلّيها|غيرها|غيّرها|حولها|حوّلها)\s+(?:على|ل|لـ)?\s*([^،,.;؛]+?)(?:\s+بدل\b|$)", text, re.I)
        if m:
            candidate = self._clean_keyword(m.group(1))
            if candidate and not re.search(r"(?:الساعة|وقت|بوست|منشور|اعلان|إعلان)", candidate, re.I):
                return candidate
        return ""

    @staticmethod
    def _coerce_context(context_plan: SmartPlan | Mapping[str, Any] | None) -> SmartPlan | None:
        if context_plan is None:
            return None
        if isinstance(context_plan, SmartPlan):
            return context_plan
        try:
            data = dict(context_plan)
        except Exception:
            return None
        weekdays = data.get("weekdays", [])
        if isinstance(weekdays, str):
            try:
                weekdays = json.loads(weekdays or "[]")
            except Exception:
                weekdays = []
        try:
            return SmartPlan(
                name=str(data.get("name") or ""),
                command_text=str(data.get("command_text") or ""),
                source_page_url=str(data.get("source_page_url") or ""),
                weekdays=[int(x) for x in (weekdays or []) if 0 <= int(x) <= 6],
                run_time=str(data.get("run_time") or "20:00"),
                run_once_at=str(data.get("run_once_at") or ""),
                post_mode="rotation" if data.get("post_mode") == "rotation" else "fixed",
                post_offset=max(0, int(data.get("post_offset") or 0)),
                group_keyword=str(data.get("group_keyword") or ""),
                max_groups=max(1, int(data.get("max_groups") or 100)),
                interval_seconds=max(30, int(data.get("interval_seconds") or 60)),
                no_repeat_days=max(0, int(data.get("no_repeat_days") or 14)),
                share_mode=str(data.get("share_mode") or "native_share"),
            )
        except Exception:
            return None

    def parse_many(
        self,
        command: str,
        default_source_page: str = "",
        default_interval: int = 60,
        default_max_groups: int = 100,
        default_no_repeat_days: int = 14,
        context_plan: SmartPlan | Mapping[str, Any] | None = None,
    ) -> list[SmartPlan]:
        raw = (command or "").strip()
        if not raw:
            raise SmartPlannerError("اكتب أمرًا للحملة أولًا." if self.language == "ar" else "Enter a campaign instruction first.")
        text = self.normalize(raw)
        context = self._coerce_context(context_plan)
        whole_source = self._extract_url(text) or (default_source_page or "").strip() or (context.source_page_url if context and self.is_followup(text) else "")

        # Short follow-ups modify the current preview as one plan; splitting them
        # by weekday aliases would lose context.
        if context and self.is_followup(text):
            return [self.parse(text, whole_source, default_interval, default_max_groups, default_no_repeat_days, context_plan=context)]

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
        context_plan: SmartPlan | Mapping[str, Any] | None = None,
    ) -> SmartPlan:
        raw = (command or "").strip()
        if not raw:
            raise SmartPlannerError("اكتب أمرًا للحملة أولًا." if self.language == "ar" else "Enter a campaign instruction first.")
        text = self.normalize(raw)
        context = self._coerce_context(context_plan)
        followup = bool(context and self.is_followup(text))

        source = self._extract_url(text) or (default_source_page or "").strip()
        if not source and followup and context:
            source = context.source_page_url
        if not source:
            raise SmartPlannerError(
                "حدد رابط صفحة المصدر مرة واحدة قبل اعتماد الأمر." if self.language == "ar"
                else "Set the source Facebook page URL before approving this instruction."
            )

        # Post selection.
        if followup and context and not self._has_post_cue(text):
            mode, offset = context.post_mode, context.post_offset
        else:
            mode, offset = self._parse_post(text)

        # Time and schedule. Follow-ups inherit unspecified pieces.
        if self._has_explicit_time(text):
            run_time = self._parse_time(text, context.run_time if context else "20:00")
            # In a short follow-up, an hour without AM/PM inherits the previous
            # part of day. Example: a 20:00 plan + "خليها الساعة 9" => 21:00.
            if followup and context and not re.search(r"(?:مساء|صباح|\bpm\b|\bam\b)", text, re.I):
                try:
                    parsed_h, parsed_m = [int(x) for x in run_time.split(":", 1)]
                    ctx_h = int(context.run_time.split(":", 1)[0])
                    if ctx_h >= 12 and parsed_h < 12:
                        parsed_h += 12
                    elif ctx_h < 12 and parsed_h == 12:
                        parsed_h = 0
                    run_time = f"{parsed_h:02d}:{parsed_m:02d}"
                except Exception:
                    pass
        elif followup and context:
            run_time = context.run_time
        else:
            run_time = self._parse_time(text, "20:00")

        if self._has_date_cue(text):
            run_once_at = self._parse_once_at(text, run_time)
            weekdays: list[int] = []
        elif followup and context:
            weekdays = list(context.weekdays)
            run_once_at = context.run_once_at
            if run_once_at and self._has_explicit_time(text):
                old = datetime.fromisoformat(run_once_at)
                hour, minute = [int(x) for x in run_time.split(":", 1)]
                updated = old.replace(hour=hour, minute=minute, second=0, microsecond=0)
                if updated <= datetime.now():
                    raise SmartPlannerError("الموعد المعدل مضى بالفعل." if self.language == "ar" else "The edited time has already passed.")
                run_once_at = updated.isoformat()
        else:
            weekdays = self._parse_weekdays(text)
            run_once_at = ""

        # Target groups. Empty keyword is allowed only when "all groups" is
        # explicit. A phrase implying a filter must never silently fall back to
        # every saved group.
        mentions_groups = self._mentions_groups(text)
        all_groups = self._explicit_all_groups(text)
        filter_hint = self._has_group_filter_hint(text)
        # Explicit all-groups wording takes precedence over the shorthand
        # extractor, but only when no filter language is present. This avoids
        # treating words like "المحفوظة" as a target keyword.
        keyword = "" if (all_groups and not filter_hint) else self._parse_group_keyword(text)
        if followup and context and not mentions_groups and not keyword:
            keyword = context.group_keyword
        elif mentions_groups and not keyword:
            if all_groups and not filter_hint:
                keyword = ""
            else:
                raise SmartPlannerError(
                    "فهمت أنك تريد فلترة الجروبات، لكن لم أستطع تحديد الكلمة المطلوبة. اكتب مثلًا: الجروبات التي يوجد في اسمها كلمة خلدة."
                    if self.language == "ar"
                    else "A group filter is implied, but the target keyword was not understood. Example: groups whose name contains Fuheis."
                )
        elif not mentions_groups and not keyword and not followup:
            raise SmartPlannerError(
                "حدد الجروبات المستهدفة بوضوح: مثل «كل الجروبات» أو «الجروبات التي يوجد في اسمها خلدة»."
                if self.language == "ar"
                else "Specify the target groups explicitly, e.g. 'all groups' or 'groups whose name contains Fuheis'."
            )

        # If a filter phrase was clearly present, never accept an empty keyword.
        if filter_hint and not keyword:
            raise SmartPlannerError(
                "لم أتعرف على كلمة فلترة الجروبات، لذلك لن أحول الأمر إلى كل الجروبات تلقائيًا."
                if self.language == "ar"
                else "The group filter keyword was not understood, so the agent will not default to all groups."
            )

        if followup and context and not self._has_interval_cue(text):
            interval = context.interval_seconds
        else:
            interval = self._parse_interval(text, default_interval)
        if followup and context and not self._has_max_groups_cue(text):
            max_groups = context.max_groups
        else:
            max_groups = self._parse_max_groups(text, default_max_groups)
        if followup and context and not self._has_no_repeat_cue(text):
            no_repeat = context.no_repeat_days
        else:
            no_repeat = self._parse_no_repeat_days(text, default_no_repeat_days)

        rule_name = name.strip() if name else self._suggest_name(weekdays, keyword, run_time)
        return SmartPlan(
            name=rule_name,
            command_text=raw,
            source_page_url=source,
            weekdays=weekdays,
            run_time=run_time,
            run_once_at=run_once_at,
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
    return (now + timedelta(days=1)).replace(hour=hour, minute=minute, second=0, microsecond=0).isoformat()
