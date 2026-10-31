import requests
from yaa_lite.ai.profiles import QWEN
from yaa_lite.ai.runtime import LocalAIRuntime, _parse_json_object


def test_runtime_retries_twice_with_progressively_safer_modes(monkeypatch):
    runtime = LocalAIRuntime(context_tokens=2048, threads=2, retry_count=2, prewarm=False)
    calls=[]; stops=[]
    def fake_chat(profile,messages,max_tokens,timeout,status,safe_mode,temperature=0.25,system_prompt=None):
        calls.append(int(safe_mode))
        if int(safe_mode) < 2:
            raise requests.ConnectionError("connection dropped")
        return "تم"
    monkeypatch.setattr(runtime,"_chat_completion",fake_chat)
    monkeypatch.setattr(runtime,"stop",lambda wait=True: stops.append(wait))
    monkeypatch.setattr(runtime,"_write_log",lambda message:None)
    assert runtime.chat(QWEN,[],128,30)=="تم"
    assert calls==[0,1,2]
    assert stops==[True,True]


def test_runtime_configuration_is_capped_for_low_memory():
    runtime=LocalAIRuntime(context_tokens=9999,threads=16,retry_count=9,prewarm=False)
    assert runtime.context_tokens==4096
    assert runtime.threads==4
    assert runtime.retry_count==2


def test_json_list_tool_call_is_parsed():
    obj = _parse_json_object('[{"name":"respond","arguments":{"message":"هلا"}}]')
    assert obj["name"] == "respond"
    assert obj["arguments"]["message"] == "هلا"


def test_empty_tool_list_degrades_to_normal_response():
    assert _parse_json_object("[]")["name"] == "respond"
