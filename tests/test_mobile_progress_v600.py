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

def test_invalid_progress_state_is_rejected(tmp_path):
    server = MobileServer('a'*48, Handler(), tmp_path, port=0)
    with pytest.raises(MobileServerError):
        server.publish('No', progress={'state':'published','step':1})


def test_progress_task_id_and_order_are_preserved(tmp_path):
    server = MobileServer('a'*48, Handler(), tmp_path, port=0)
    first = server.publish('Opening browser', progress={'state':'started','step':0,'task_id':'task_12345678'})
    second = server.publish('Browser open', progress={'state':'working','step':1,'task_id':'task_12345678'})
    assert second['id'] > first['id']
    assert second['progress']['task_id'] == first['progress']['task_id']
    assert [e['id'] for e in server._snapshot(0)['events']] == [first['id'], second['id']]

@pytest.mark.parametrize('bad', ['spaces not allowed', '../invalid', 'x'*65, 123])
def test_progress_rejects_bad_task_id(tmp_path, bad):
    server = MobileServer('a'*48, Handler(), tmp_path, port=0)
    with pytest.raises(MobileServerError):
        server.publish('Step', progress={'state':'working','step':1,'task_id':bad})

@pytest.mark.parametrize('bad', [-1, 101, True, '1'])
def test_progress_rejects_invalid_step(tmp_path, bad):
    server = MobileServer('a'*48, Handler(), tmp_path, port=0)
    with pytest.raises(MobileServerError):
        server.publish('Step', progress={'state':'working','step':bad})
