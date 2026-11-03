YourAssistantAgent - Android startup crash mitigation

1. Extract this ZIP.
2. Copy APPLY-ANDROID-STARTUP-FIX.py and APPLY-ANDROID-STARTUP-FIX.bat into the root of your local YourAssistantAgent GitHub Desktop checkout (same folder as android/).
3. Double-click APPLY-ANDROID-STARTUP-FIX.bat (Python must be installed).
4. Confirm DONE, then GitHub Desktop > Commit to main > Push origin.
5. Wait for Android GitHub Actions build and install NEW APK.

This patch prevents automatic native voice engine startup at app launch and catches unexpected errors during periodic event rendering. It does NOT prove the cause of the crash without Android crash logs.

The bundled female voice is not eagerly initialized by this mitigation. Text chat and QR remain enabled; voice may fall back to Android system TTS when a call is started. This tradeoff is deliberate to isolate startup crashes.
