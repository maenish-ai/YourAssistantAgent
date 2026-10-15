from yaa_lite.ai.engine import ChatEngine
from yaa_lite.ai.profiles import get_profile

class RuntimeShouldNotRun:
    def chat(self, *a, **k):
        raise AssertionError("fast-path must not load AI")

def test_arabic_greeting_is_instant():
    e = ChatEngine(RuntimeShouldNotRun())
    r = e.reply(get_profile("arabic"), [], "كيف حالك؟", 128, 10)
    assert not r.used_model
    assert "جاهز" in r.text


def test_arabic_ahlan_is_instant():
    e = ChatEngine(RuntimeShouldNotRun())
    r = e.reply(get_profile("arabic"), [], "أهلا", 128, 10)
    assert not r.used_model
    assert "أهل" in r.text
