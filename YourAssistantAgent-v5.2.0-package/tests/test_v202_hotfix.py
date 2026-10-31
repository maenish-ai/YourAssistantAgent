import json

from yaa_lite.hotfix_v202 import _compact_messages, _decode_hammer_call


def test_empty_hammer_tool_list_is_no_tool_not_protocol_crash():
    name, args, empty = _decode_hammer_call("[]")
    assert name == "respond"
    assert args == {}
    assert empty is True


def test_valid_hammer_tool_call_still_routes():
    raw = json.dumps([{"name": "facebook_status", "arguments": {}}])
    name, args, empty = _decode_hammer_call(raw)
    assert name == "facebook_status"
    assert args == {}
    assert empty is False


def test_router_history_is_compacted():
    messages = [{"role": "system", "content": "prefs"}]
    messages += [{"role": "user", "content": "x" * 2000} for _ in range(8)]
    compact = _compact_messages(messages, total_chars=2400, per_message=900)
    assert compact[0]["role"] == "system"
    assert len(compact) <= 4
    assert sum(len(m["content"]) for m in compact) <= 2400
