from datetime import datetime
from your_assistant_agent.db import Database


def test_compute_next_run_is_future():
    out = Database.compute_next_run(3, "20:00")
    assert datetime.fromisoformat(out) > datetime.now()
