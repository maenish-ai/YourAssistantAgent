YourAssistantAgent - fix for run 41581298413 / Windows job 125736524935

Root cause verified in GitHub Actions logs:
  tests/test_packaging_branding_v143.py::test_only_one_active_workflow_is_shipped
  Expected only build-windows.yml; android-female-voice.yml is still present.
  491 tests passed, 3 skipped, 1 failed.

1. Copy APPLY-FIX.bat and APPLY-FIX.ps1 to the REPOSITORY ROOT (same folder as .git).
2. Double-click APPLY-FIX.bat.
3. In GitHub Desktop, verify the deletion of .github/workflows/android-female-voice.yml.
4. Commit to main and Push origin. Ensure the commit contains the deletion.
5. Wait for the new GitHub Actions run.

Do NOT upload this ZIP as a GitHub release or commit it alone: scripts must run in your local repository.
No Windows or Android source files are changed; the duplicate workflow is deleted.
A successful full build cannot be guaranteed until the new CI run completes.
