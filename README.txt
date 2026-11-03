Android crash-resilience patch for YourAssistantAgent
1) Extract APPLY-ANDROID-FIX.py and APPLY-ANDROID-FIX.bat into your GitHub Desktop repository root (the folder containing .git and android).
2) Double-click APPLY-ANDROID-FIX.bat. It must say DONE.
3) In GitHub Desktop, verify MainActivity.java is modified, Commit to main, Push origin.
4) Wait for Android build to succeed. Download and install the NEW APK from GitHub Actions artifacts; old installed APK does not change when source code is pushed.
This addresses unhandled errors in periodic event refresh and async TTS initialization. It is not proof of the underlying device crash cause; Android crash logs and device testing remain necessary to guarantee resolution.
