YourAssistantAgent Android 1.8.10 patch
Copy both APPLY files to the root of your cloned repository (same folder as android/), then run the BAT file. Requires Python 3.
Verify DONE and GitHub Desktop shows three changed files. Commit and Push. Build a NEW APK from GitHub Actions and verify About/version is 1.8.10.
Changes: startup voice isolation, on-device Java crash capture, startup stage, diagnostic report button, Android exit reasons on API 30+.
Limitations: native crashes or OS kills may not yield a Java stack trace. No automatic upload to Windows. No APK build or device test was performed.
