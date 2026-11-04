Android Startup Crash Isolation Patch v2

1) Open GitHub Desktop > Repository > Show in Explorer.
2) Copy both APPLY-ANDROID-STARTUP-FIX.py and .bat into the ROOT folder of YourAssistantAgent.
3) Double-click APPLY-ANDROID-STARTUP-FIX.bat.
4) Confirm DONE; commit only android/app/src/main/java/ai/maenish/yourassistant/MainActivity.java.
5) Push origin. Wait for a successful Android build and install the NEW APK.
6) First test: open the app and leave it untouched for 20 seconds.

The patch defers both voice engines until the user explicitly starts a voice call.
This is a targeted hypothesis test, not a guaranteed fix. It does not modify Windows.
If the app still closes, collect a crash log using Android's bug report feature (no Android Studio needed).
Do not share full bug reports publicly; they may contain sensitive information.
