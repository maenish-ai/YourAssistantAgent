from pathlib import Path
from yaa_lite.remote.mobile import MobileServer, MobileServerError
import pytest

class Handler:
    pass

def test_progress_event_has_machine_readable_state(tmp_path):
    server = MobileServer('a'*48, Handler(), tmp_path, port=0)
    event = server.publish('Step 1', progress={'state':'working','step':1})
    assert event['type'] == 'progress'
    assert event['progress'] == {'state':'working','step':1}
    assert event['text'] == 'Step 1'


def test_unverified_result_is_not_marked_as_completed(tmp_path):
    server = MobileServer('a'*48, Handler(), tmp_path, port=0)
    event = server.publish('Verify externally', progress={'state':'unverified','step':0})
    assert event['progress']['state'] == 'unverified'

def test_invalid_progress_state_is_rejected(tmp_path):
    server = MobileServer('a'*48, Handler(), tmp_path, port=0)
    with pytest.raises(MobileServerError):
        server.publish('No', progress={'state':'published','step':1})
