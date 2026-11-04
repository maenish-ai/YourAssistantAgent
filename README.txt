SMART CRASH DIAGNOSTICS v1

1. Extract these two files to repository root (same folder as android).
2. Run APPLY-SMART-DIAGNOSTICS.bat with Python installed.
3. Commit & push Android changes, build APK in GitHub Actions.
4. Open app, wait 20 sec. If it crashes, reopen, tap "تقرير الأعطال / تشخيص التطبيق", and share the report.

Privacy: local-only diagnostics; no automatic upload. No tokens, URLs, message text or exception messages are stored.
Limitations: uncaught Java exceptions can be logged, but native crashes/OS kills may only show the last startup stage.
This patch has not been compiled or tested on a physical device.
