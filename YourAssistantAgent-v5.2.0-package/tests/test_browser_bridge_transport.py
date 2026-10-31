"""Exercise the real loopback transport without a browser or Facebook account."""
from concurrent.futures import ThreadPoolExecutor
import json
import threading
import time
from urllib.request import Request, urlopen

import pytest

from yaa_lite.browser_bridge.server import BrowserBridge


def request(bridge, path, data=None):
    raw = json.dumps(data).encode() if data is not None else None
    with urlopen(Request(f"http://127.0.0.1:{bridge.port}{path}", data=raw,
                         headers={"Content-Type": "application/json"}), timeout=2) as response:
        return json.load(response)


@pytest.fixture
def bridge():
    instance = BrowserBridge(port=0)
    assert instance.start()
    request(instance, "/hello", {"browser": "test browser", "tabs": 2})
    yield instance
    instance.stop()


def next_command(bridge):
    deadline = time.monotonic() + 2
    while time.monotonic() < deadline:
        command = request(bridge, "/next-command")["command"]
        if command:
            return command
        threading.Event().wait(.005)
    raise AssertionError("No command queued")


def test_discovery_works_without_launcher_monkey_patches(bridge):
    with ThreadPoolExecutor() as executor:
        pending = executor.submit(bridge.execute, "discover_facebook_groups", limit=9000, deep=True)
        command = next_command(bridge)
        assert command["arguments"] == {"limit": 1000, "deep": True}
        assert command["expires_at"] > time.time()
        response = {"ok": True, "groups": [{"name": "My group", "url": "https://www.facebook.com/groups/123"}]}
        request(bridge, "/command-result", {"id": command["id"], "result": response})
        assert pending.result(timeout=2) == response
    assert not bridge._commands
    assert not bridge._results
    assert not bridge._result_events


def test_timed_out_click_is_removed_and_late_result_is_ignored(bridge):
    with pytest.raises(TimeoutError):
        bridge.execute("click_text", text="Post", timeout=.01)
    assert request(bridge, "/next-command")["command"] is None
    result = request(bridge, "/command-result", {"id": "expired-id", "result": {"ok": True}})
    assert result["ignored"]
    assert not bridge._results
    assert not bridge._result_events


def test_session_probe_result_round_trip(bridge):
    with ThreadPoolExecutor() as executor:
        pending = executor.submit(bridge.execute, "facebook_session")
        command = next_command(bridge)
        assert command["action"] == "facebook_session"
        result = {"ok": True, "status": "not_connected"}
        request(bridge, "/command-result", {"id": command["id"], "result": result})
        assert pending.result(timeout=2) == result


def test_non_allowlisted_command_is_rejected(bridge):
    with pytest.raises(ValueError):
        bridge.execute("eval", script="alert('no')")
