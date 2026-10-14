import sys
import types
from pathlib import Path

# facebook.py only needs asset_path from branding for bundled-browser lookup.
# The CI/unit-test path here does not need Qt, so stub branding to keep this
# parser test independent from the optional desktop GUI dependency.
branding = types.ModuleType("your_assistant_agent.branding")
branding.asset_path = lambda name: Path("/nonexistent") / name
sys.modules.setdefault("your_assistant_agent.branding", branding)

from your_assistant_agent.facebook import FacebookAutomation


def test_normalize_group_candidate_numeric_link():
    item = FacebookAutomation._normalize_group_candidate(
        "https://www.facebook.com/groups/123456789/?ref=share",
        "Amman Satellite Group\nPrivate group · 12K members",
    )
    assert item == {
        "name": "Amman Satellite Group",
        "url": "https://www.facebook.com/groups/123456789",
        "tags": "",
    }


def test_normalize_group_candidate_uses_aria_and_rejects_navigation():
    item = FacebookAutomation._normalize_group_candidate(
        "/groups/fuheis.market/posts/123/",
        "",
        "Fuheis Market",
    )
    assert item["name"] == "Fuheis Market"
    assert item["url"] == "https://www.facebook.com/groups/fuheis.market"
    assert FacebookAutomation._normalize_group_candidate(
        "https://www.facebook.com/groups/joins/", "Your groups"
    ) is None
