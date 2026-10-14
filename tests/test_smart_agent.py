from datetime import datetime

from your_assistant_agent.smart_agent import SmartPlanner, calculate_next_run


def test_arabic_weekly_latest_half_minute():
    planner = SmartPlanner("ar")
    plan = planner.parse(
        "كل يوم الاثنين الساعة 8 مساء خذ آخر بوست وشاركه على كل الجروبات اللي اسمها يحتوي الفحيص، كل نص دقيقة",
        default_source_page="https://www.facebook.com/examplepage",
    )
    assert plan.weekdays == [0]
    assert plan.run_time == "20:00"
    assert plan.post_mode == "fixed"
    assert plan.post_offset == 0
    assert plan.group_keyword == "الفحيص"
    assert plan.interval_seconds == 30
    assert plan.share_mode == "native_share"


def test_previous_post_and_rotation_detection():
    planner = SmartPlanner("ar")
    previous = planner.parse(
        "الثلاثاء الساعة 6 مساء خذ البوست اللي قبله وانشره على الجروبات اللي فيها دابوق",
        default_source_page="https://www.facebook.com/examplepage",
    )
    assert previous.weekdays == [1]
    assert previous.run_time == "18:00"
    assert previous.post_offset == 1
    assert previous.group_keyword == "دابوق"

    rotation = planner.parse(
        "كل يوم الساعة 7 مساء دور على البوستات وبعدين يرجع من الأول، الجروبات اللي فيها صويلح",
        default_source_page="https://www.facebook.com/examplepage",
    )
    assert rotation.weekdays == []
    assert rotation.post_mode == "rotation"
    assert rotation.group_keyword == "صويلح"


def test_calculate_next_run_weekly():
    now = datetime(2026, 10, 14, 15, 0)  # Wednesday
    next_run = calculate_next_run([2], "20:00", now=now)
    assert next_run == "2026-10-14T20:00:00"

def test_multiple_weekday_clauses_become_separate_rules():
    planner = SmartPlanner("ar")
    plans = planner.parse_many(
        "يوم الاثنين الساعة 8 مساء خذ آخر بوست على الجروبات اللي فيها الفحيص. يوم الثلاثاء الساعة 6 مساء خذ البوست اللي قبله على الجروبات اللي فيها دابوق",
        default_source_page="https://www.facebook.com/examplepage",
    )
    assert len(plans) == 2
    assert plans[0].weekdays == [0]
    assert plans[0].run_time == "20:00"
    assert plans[0].group_keyword == "الفحيص"
    assert plans[0].post_offset == 0
    assert plans[1].weekdays == [1]
    assert plans[1].run_time == "18:00"
    assert plans[1].group_keyword == "دابوق"
    assert plans[1].post_offset == 1
