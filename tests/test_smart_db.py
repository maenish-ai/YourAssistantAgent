from pathlib import Path

from your_assistant_agent.db import Database
from your_assistant_agent.smart_agent import SmartPlan


def test_smart_rule_queue_and_dedupe(tmp_path: Path):
    db = Database(tmp_path / "smart.sqlite")
    gid = db.add_group("الفحيص بيع وشراء", "https://www.facebook.com/groups/123", "الفحيص")
    # add_group does not return the id in legacy API; fetch it from the saved row.
    group = db.list_groups()[0]
    plan = SmartPlan(
        name="Rule",
        command_text="test",
        source_page_url="https://www.facebook.com/example",
        weekdays=[0],
        run_time="20:00",
        group_keyword="الفحيص",
        interval_seconds=30,
    )
    rid = db.add_smart_rule(plan)
    assert db.get_smart_rule(rid)["group_keyword"] == "الفحيص"
    count = db.enqueue_smart(rid, [group["id"]], "https://www.facebook.com/example/posts/1", 30)
    assert count == 1
    item = db.next_due_smart_queue_item("9999-12-31T23:59:59")
    assert item["group_name"] == "الفحيص بيع وشراء"
    db.mark_smart_queue(item["id"], "done")
    db.record_share(rid, group["id"], item["post_url"], "done")
    assert db.was_shared_recently(group["id"], item["post_url"], 14)
