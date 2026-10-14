from __future__ import annotations

import pytest

from your_assistant_agent.smart_agent import SmartPlanner, SmartPlannerError


SOURCE = "https://www.facebook.com/example"


def test_understands_arbitrary_group_keyword_and_written_arabic_time():
    plan = SmartPlanner("ar").parse(
        "غدا انشر آخر إعلان من الصفحة على جميع المجموعات التي يوجد بها كلمة خلدة وذلك على الساعة الثامنة مساء",
        SOURCE,
    )
    assert plan.group_keyword == "خلدة"
    assert plan.run_time == "20:00"
    assert plan.run_once_at


def test_understands_other_place_names_without_hardcoding():
    planner = SmartPlanner("ar")
    mahas = planner.parse(
        "كل يوم الساعة 8 مساء انشر آخر منشور على كل الجروبات اللي في اسمها ماحص",
        SOURCE,
    )
    marj = planner.parse(
        "بكرا الساعة 7:30 مساء انشر آخر بوست على جروبات مرج الحمام",
        SOURCE,
    )
    assert mahas.group_keyword == "ماحص"
    assert mahas.run_time == "20:00"
    assert marj.group_keyword == "مرج الحمام"
    assert marj.run_time == "19:30"


def test_explicit_all_groups_is_allowed():
    plan = SmartPlanner("ar").parse(
        "كل يوم الساعة 8 مساء انشر آخر منشور على جميع الجروبات المحفوظة",
        SOURCE,
    )
    assert plan.group_keyword == ""


def test_implied_filter_never_falls_back_to_all_groups():
    with pytest.raises(SmartPlannerError):
        SmartPlanner("ar").parse(
            "كل يوم الساعة 8 مساء انشر آخر منشور على المجموعات التي يوجد بها كلمة",
            SOURCE,
        )


def test_followup_keeps_context_and_changes_time():
    planner = SmartPlanner("ar")
    base = planner.parse(
        "كل يوم الساعة 8 مساء انشر آخر منشور على الجروبات التي اسمها يحتوي خلدة",
        SOURCE,
    )
    edited = planner.parse("خليها الساعة 9 بدل 8", SOURCE, context_plan=base)
    assert edited.group_keyword == "خلدة"
    assert edited.run_time == "21:00"
    assert edited.source_page_url == SOURCE


def test_followup_can_change_group_keyword_only():
    planner = SmartPlanner("ar")
    base = planner.parse(
        "كل يوم الساعة 8 مساء انشر آخر منشور على الجروبات التي اسمها يحتوي خلدة",
        SOURCE,
    )
    edited = planner.parse("خليها على صويلح بدل خلدة", SOURCE, context_plan=base)
    assert edited.group_keyword == "صويلح"
    assert edited.run_time == "20:00"
