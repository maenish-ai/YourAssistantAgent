YourAssistantAgent — CI fix for GitHub Actions run 41449042041

Root causes:
1) UnboundLocalError in RemoteAssistant.callback: remove redundant local import secrets; module already imports it.
2) Installer metadata test expects numeric MyAppVersion: use 6.0.0 while showing 6.0.0-dev in AppVerName and setup filename.

INSTALL:
Extract the ZIP at the repository root, preserving paths. Commit both changed files and push.
No tests or approval safeguards are disabled.

VERIFIED:
87 related pytest tests passed on Linux with PYTHONPATH=src.
Full test suite did not complete before timeout; Windows GitHub Actions must verify.
This fixes the 11 failures seen in the linked run; new runs could expose other issues.
