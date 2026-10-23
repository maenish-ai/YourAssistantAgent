"""Run from the repository root: python APPLY_PATCH.py"""
from pathlib import Path
import shutil

root = Path(__file__).resolve().parent
project = Path.cwd().resolve()
launcher = project / 'launcher.py'
if not launcher.is_file() or not (project / 'src/yaa_lite/text_first_v300.py').is_file():
    raise SystemExit('Run this script from the existing YourAssistantAgent repository root.')
source = root / 'src/yaa_lite/action_preview_v311.py'
target = project / 'src/yaa_lite/action_preview_v311.py'
if target.exists() and target.read_bytes() != source.read_bytes():
    raise SystemExit('Target file already exists with different content. Review manually; no overwrite performed.')
text = launcher.read_text(encoding='utf-8')
anchor = 'apply_text_first_v300()'
addition = '\nfrom yaa_lite.action_preview_v311 import apply_action_preview_v311\napply_action_preview_v311()'
if 'apply_action_preview_v311()' not in text:
    if text.count(anchor) != 1:
        raise SystemExit('Launcher structure changed. No files modified; integrate manually.')
    updated = text.replace(anchor, anchor + addition, 1)
else:
    updated = text
# Write only after all preconditions are satisfied.
if not target.exists():
    shutil.copy2(source, target)
if updated != text:
    backup = launcher.with_suffix('.py.v311.bak')
    if backup.exists():
        raise SystemExit('Backup exists; refusing to overwrite. Review manually.')
    shutil.copy2(launcher, backup)
    launcher.write_text(updated, encoding='utf-8')
print('Patch applied. Review launcher.py and action_preview_v311.py before commit.')
