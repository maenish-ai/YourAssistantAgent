"""Every supported launch path must activate the same working application."""
import os
from pathlib import Path
import subprocess
import sys

import pytest

ROOT = Path(__file__).resolve().parents[1]


@pytest.mark.parametrize('entrypoint', ['launcher', 'module', 'console'])
def test_entrypoints_apply_features_before_self_test(entrypoint):
    script = '''
import runpy
import sys
from yaa_lite.bootstrap import configure_application

sys.argv = ['your-assistant-agent', '--self-test']
try:
    if sys.argv_entry == 'launcher':
        runpy.run_path('launcher.py', run_name='__main__')
    elif sys.argv_entry == 'module':
        runpy.run_module('yaa_lite.main', run_name='__main__')
    else:
        from yaa_lite.main import main
        assert main() == 0
except SystemExit as exc:
    assert exc.code == 0

from yaa_lite.ui.chat_window import ChatWindow
from yaa_lite.ui.app import App
from yaa_lite.agent.orchestrator import SmartAgentController
assert ChatWindow._yaa_v430
assert ChatWindow._yaa_v420
assert ChatWindow._yaa_text_first_v300
assert App._yaa_v410
assert SmartAgentController._yaa_v220_patched
send = ChatWindow.send
configure_application()
assert ChatWindow.send is send, 'Initialization must not wrap handlers twice'
'''
    result = subprocess.run(
        [sys.executable, '-c', 'import sys; sys.argv_entry = ' + repr(entrypoint) + '\n' + script],
        cwd=ROOT, env={**os.environ, 'PYTHONPATH': str(ROOT / 'src')},
        capture_output=True, text=True, timeout=30,
    )
    assert result.returncode == 0, result.stdout + result.stderr
