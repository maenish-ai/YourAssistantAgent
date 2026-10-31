"""Apply from extracted bundle: python APPLY_PATCH.py <path-to-project>.
No silent overwrite: launcher and config backups created before edits.
"""
import sys
import shutil
from pathlib import Path

bundle = Path(__file__).resolve().parent
project = Path(sys.argv[1]).resolve() if len(sys.argv) > 1 else Path.cwd().resolve()
launcher = project / 'launcher.py'
config = project / 'src/yaa_lite/config.py'
if not launcher.is_file() or not config.is_file() or not (project / 'src/yaa_lite/text_first_v300.py').is_file():
    raise SystemExit('Provide the root of YourAssistantAgent repository as argument or current directory.')
source_files = ['src/yaa_lite/windows_discovery_v400.py', 'src/yaa_lite/discovery_ui_v400.py', 'tests/test_discovery_v400.py']
for name in source_files:
    dst = project / name
    if dst.exists() and dst.read_bytes() != (bundle / name).read_bytes():
        raise SystemExit('Refusing to overwrite a modified file: ' + name)
text = launcher.read_text(encoding='utf-8')
anchor = 'apply_text_first_v300()'
addition = '\nfrom yaa_lite.discovery_ui_v400 import apply_discovery_ui_v400\napply_discovery_ui_v400()'
if 'apply_discovery_ui_v400()' not in text:
    if text.count(anchor) != 1:
        raise SystemExit('Launcher changed; no modifications made.')
    text = text.replace(anchor, anchor + addition, 1)
old = config.read_text(encoding='utf-8')
new = old.replace('close_behavior: str = "exit"', 'close_behavior: str = "ask"', 1)
# Existing user settings may override default. Never alter their saved settings.
if text != launcher.read_text(encoding='utf-8') and launcher.with_suffix('.py.v400.bak').exists():
    raise SystemExit('Launcher backup already exists; aborting.')
if new != old and config.with_suffix('.py.v400.bak').exists():
    raise SystemExit('Config backup already exists; aborting.')
for name in source_files:
    dst = project / name
    dst.parent.mkdir(parents=True, exist_ok=True)
    if not dst.exists():
        shutil.copy2(bundle / name, dst)
if text != launcher.read_text(encoding='utf-8'):
    shutil.copy2(launcher, launcher.with_suffix('.py.v400.bak'))
    launcher.write_text(text, encoding='utf-8')
if new != old:
    shutil.copy2(config, config.with_suffix('.py.v400.bak'))
    config.write_text(new, encoding='utf-8')
print('Applied v4 discovery patch. Review git diff and run tests before commit.')
