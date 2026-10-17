from yaa_lite.config import Settings


def test_defaults_are_4gb_friendly_but_tool_capable():
    s = Settings()
    assert s.context_tokens <= 3072
    assert s.threads <= 2
    assert s.max_response_tokens <= 240
    assert s.hammer_idle_minutes == 0
