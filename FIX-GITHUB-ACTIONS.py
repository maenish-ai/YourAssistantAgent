from pathlib import Path
import sys

root = Path(__file__).resolve().parent
workflow = root / '.github/workflows/build-windows.yml'
duplicate = root / '.github/workflows/android-female-voice.yml'
if not workflow.is_file():
    sys.exit('ERROR: Put the ZIP contents in the repository root (next to android/ and .github/).')
content = workflow.read_text(encoding='utf-8')
marker = '      - name: Restore private Android release key when configured'
install = '''      - uses: actions/setup-python@v5
        with:
          python-version: '3.11'
      - name: Install bundled voice model converter
        run: python -m pip install 'onnx==1.17.0'
'''
if 'Install bundled voice model converter' not in content:
    if content.count(marker) != 1:
        sys.exit('ERROR: Cannot safely locate the Android build step; no files changed.')
    content = content.replace(marker, install + marker, 1)
# Keep original Windows workflow guard, now it will see exactly one workflow.
workflow.write_text(content, encoding='utf-8')
if duplicate.exists():
    duplicate.unlink()
    print('Removed duplicate Android workflow.')
else:
    print('Duplicate Android workflow already absent.')
print('Added ONNX dependency to main Android job (or already present).')
print('Next: GitHub Desktop -> Commit -> Push origin.')
