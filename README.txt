YourAssistantAgent - GitHub Desktop Actions repair

1. In GitHub Desktop: Repository > Show in Explorer.
2. Copy APPLY-FIX.bat and APPLY-FIX.ps1 into that repository folder, next to android and .github.
3. Double-click APPLY-FIX.bat.
4. In GitHub Desktop, Commit to main and Push origin.

This fixes two errors from run 41505278135:
- Removes duplicate android-female-voice.yml (and old windows-build.yml if present).
- Installs onnx==1.17.0 in the Android job in build-windows.yml.

This does not guarantee the Android model conversion or APK runtime will work; check the next Actions run.
