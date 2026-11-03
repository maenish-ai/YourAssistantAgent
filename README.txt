Windows GitHub Actions red-X repair

1. Extract both APPLY-WINDOWS-FIX files into the ROOT of your GitHub Desktop repository, next to .git and .github.
2. Double-click APPLY-WINDOWS-FIX.bat.
3. In GitHub Desktop, confirm that .github/workflows/android-female-voice.yml is DELETED and build-windows.yml is MODIFIED.
4. Commit to main and PUSH ORIGIN. Deleting a file locally without pushing does not affect GitHub Actions.

This patch removes the duplicate workflow and the unnecessary one-workflow-only check. It does not alter the Windows application code. Future CI errors may require separate fixes.
