Android 1.8.0 startup isolation patch
1. Copy both APPLY files into the root of YourAssistantAgent repository.
2. Run APPLY-ANDROID-1.8.0.bat. Requires Python 3.
3. Verify DONE, then commit and push both changed files with GitHub Desktop.
4. Wait for GitHub Actions build; install NEW APK.
This patch postpones voice initialization until the user starts a voice call. It does not guarantee resolution of every crash and does not add crash-reporting instrumentation.
