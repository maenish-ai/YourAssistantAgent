from yaa_lite.ai.engine import ChatEngine, quick_reply
from yaa_lite.ai.profiles import get_profile


class FakeRuntime:
    def __init__(self):
        self.calls = 0
    def chat(self, *a, **k):
        self.calls += 1
        return "أنا تمام، شو بتحب نعمل؟"


def test_every_greeting_goes_through_hammer():
    rt = FakeRuntime()
    e = ChatEngine(rt)
    r = e.reply(get_profile("hammer"), [], "كيف حالك؟", 128, 10)
    assert r.used_model
    assert rt.calls == 1
    assert "تمام" in r.text


def test_no_hidden_fast_reply_path():
    assert quick_reply("أهلا") is None
    assert quick_reply("hello") is None
