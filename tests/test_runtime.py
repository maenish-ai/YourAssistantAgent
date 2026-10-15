from yaa_lite.ai.runtime import _strip_reasoning

def test_strip_reasoning():
    assert _strip_reasoning("<think>secret</think>hello") == "hello"
