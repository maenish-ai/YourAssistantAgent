import requests
from yaa_lite.ai.profiles import HAMMER
from yaa_lite.ai.runtime import LocalAIRuntime, _parse_json_object


def test_runtime_retries_twice_with_progressively_safer_modes(monkeypatch):
    runtime = LocalAIRuntime(context_tokens=768, threads=2, retry_count=2)
    calls=[]; stops=[]
    def fake_post(profile,messages,tools,max_tokens,timeout,status,safe_mode):
        calls.append(int(safe_mode))
        if int(safe_mode) < 2:
            raise requests.ConnectionError("connection dropped")
        return '[{"name":"respond","arguments":{"message":"تم"}}]'
    monkeypatch.setattr(runtime,"_hammer_completion",fake_post)
    monkeypatch.setattr(runtime,"stop",lambda wait=True: stops.append(wait))
    monkeypatch.setattr(runtime,"_write_log",lambda message:None)
    assert runtime.chat(HAMMER,[],128,30)=="تم"
    assert calls==[0,1,2]
    assert stops==[True,True]


def test_runtime_configuration_is_capped_for_4gb():
    runtime=LocalAIRuntime(context_tokens=4096,threads=16,retry_count=9)
    assert runtime.context_tokens==2048
    assert runtime.threads==2
    assert runtime.retry_count==2


def test_hammer_native_json_list_tool_call_is_parsed():
    obj = _parse_json_object('[{"name":"respond","arguments":{"message":"هلا"}}]')
    assert obj["name"] == "respond"
    assert obj["arguments"]["message"] == "هلا"

def test_hammer_empty_tool_list_means_no_tool():
    assert _parse_json_object("[]") is None
