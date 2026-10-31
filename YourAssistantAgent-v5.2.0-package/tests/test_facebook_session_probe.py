from types import SimpleNamespace

import pytest

from yaa_lite.agent.facebook_service import FacebookService, FacebookActionResult
from yaa_lite.fast_live_v250 import fast_check_facebook


class ProbeBridge:
    connected = True

    def __init__(self, result):
        self.result = result

    def execute(self, action, **arguments):
        assert action == "facebook_session"
        return self.result


@pytest.mark.parametrize("state,ok,expected", [
    ("connected", True, True),
    ("not_connected", True, False),
    ("checkpoint", True, False),
    ("unknown", False, False),
])
def test_service_requires_positive_session_evidence(state, ok, expected):
    service = FacebookService(None, SimpleNamespace(interface_language="en"),
                              activity=lambda *_: None,
                              browser_bridge=ProbeBridge({"ok": ok, "status": state}))
    result = service._verify_via_open_browser()
    assert result.ok is expected
    assert (service.status_code() == "connected") is expected


def test_http_success_alone_never_means_signed_in():
    service = FacebookService(None, SimpleNamespace(interface_language="en"),
                              activity=lambda *_: None,
                              browser_bridge=ProbeBridge({"ok": True, "status": 200, "url": "https://www.facebook.com/me"}))
    assert not service._verify_via_open_browser().ok
    assert service.status_code() != "connected"
    service._last_status = "connected"
    service.open_manual_login = lambda: FacebookActionResult(True, 'Opened controlled sign-in window')
    text = fast_check_facebook(service)
    assert service.status_code() != "connected"
    assert "Could not verify" in text or "could not" in text.lower()
    assert 'Opened controlled sign-in window' in text
