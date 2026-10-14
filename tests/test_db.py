import tempfile
from pathlib import Path

from your_assistant_agent.db import Database


def test_groups_campaign_and_queue():
    with tempfile.TemporaryDirectory() as td:
        db = Database(Path(td) / "t.db")
        db.add_group("Dabouq 1", "https://www.facebook.com/groups/1", "دابوق")
        db.add_group("Sweileh 1", "https://www.facebook.com/groups/2", "صويلح")
        assert len(db.list_groups(enabled_only=True, keyword="دابوق")) == 1

        db.add_campaign(
            "Test", "https://www.facebook.com/example", 0, "دابوق", 10, 30, 3, "20:00"
        )
        camps = db.list_campaigns()
        assert len(camps) == 1
        groups = db.list_groups(enabled_only=True, keyword="دابوق", limit=10)
        n = db.enqueue(camps[0]["id"], [g["id"] for g in groups], "https://facebook.com/example/posts/1", 30)
        assert n == 1
        stats = db.queue_stats()
        assert stats["pending"] == 1
