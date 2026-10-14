import tempfile
from pathlib import Path

from your_assistant_agent.db import Database
from your_assistant_agent.text_utils import normalize_search


def test_arabic_unicode_normalization():
    assert normalize_search("أَلْف حَرَس") == normalize_search("الف حرس")
    assert normalize_search("إعلان SATELLITE") == normalize_search("اعلان satellite")


def test_whatsapp_contacts_and_batching():
    with tempfile.TemporaryDirectory() as td:
        db = Database(Path(td) / "t.db")
        for i in range(205):
            db.add_wa_contact(f"عميل {i}", f"96279000{i:04d}", "عملاء عمان", True)
        eligible = db.list_wa_contacts(enabled_only=True, opted_in_only=True, keyword="عمان")
        assert len(eligible) == 205
        db.add_wa_campaign("عرض", "text", "عرض اليوم", "", "ar", "عمان", 100, 30, 1, "19:00")
        camp = db.list_wa_campaigns()[0]
        count, batches = db.enqueue_wa(camp["id"], [c["id"] for c in eligible], 100, 30)
        assert count == 205
        assert batches == 3
