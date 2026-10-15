from yaa_lite.config import Settings

def test_defaults_are_4gb_friendly():
    s = Settings()
    assert s.context_tokens <= 1024
    assert s.threads <= 2
    assert s.max_response_tokens <= 220
