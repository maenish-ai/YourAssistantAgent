"""Advice questions must stay conversational through the shipped patch stack."""
from pathlib import Path
import subprocess
import sys

import pytest


@pytest.mark.parametrize('message', [
    'شو رأيك نفحص اتصال فيسبوك؟',
    'شو رأيك افتح GitHub Desktop؟',
    'شو رأيك ألغي المهمة؟',
])
def test_full_bootstrap_advice_does_not_execute_or_cancel(tmp_path, message):
    script = r'''
from pathlib import Path
from types import SimpleNamespace
import sys
from yaa_lite.bootstrap import configure_application
configure_application()
from yaa_lite.agent.orchestrator import SmartAgentController
from yaa_lite.config import Settings
from yaa_lite.storage.db import ChatDB
db=ChatDB(Path(sys.argv[1])); session=db.create_session('hammer')
db.set_pending_action(session,'approve_facebook_campaign',{'plan':{}},'Pending preview')
def unexpected(*args, **kwargs): raise AssertionError('Advice must not invoke tools')
def reply(*args, **kwargs): return SimpleNamespace(text='خلينا نقارن الخيارات أولاً')
engine=SimpleNamespace(reply=reply,runtime=SimpleNamespace(native_turn=unexpected))
controller=SmartAgentController(db,Settings(),engine,SimpleNamespace())
result=controller.handle(None,[],sys.argv[2],session,256,10)
assert result.text=='خلينا نقارن الخيارات أولاً'
assert db.get_pending_action(session) is not None
'''
    root = Path(__file__).resolve().parents[1]
    result = subprocess.run([sys.executable, '-c', script, str(tmp_path/'db.sqlite'), message],
                            cwd=root, capture_output=True, text=True, timeout=15)
    assert result.returncode == 0, result.stdout + result.stderr
