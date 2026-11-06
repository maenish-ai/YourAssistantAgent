# Architecture audit — development snapshot

Date: 2026-11-05. Base: `origin/main` at `fce07d0`; working branch `development/assistant-6-foundation`. The remote exposes one branch, `main`; 91 commits were present after fetching. This is an evidence-led initial audit, not an exhaustive file-by-file security certification.

## Components and flow

- Windows entry `launcher.py` → `src/yaa_lite/main.py` → `bootstrap.py` installs historical compatibility patches → Tk UI `ui/` and SQLite `storage/db.py`. The layering and patches in `personal_assistant_v220.py`, `text_first_v300.py`, and versioned files can change behavior after import; trace the configured runtime, not just individual classes.
- AI: `ai/runtime.py` calls Groq Chat Completions; `agent/orchestrator.py` and its patched controllers select tools. The desktop loop `remote/desktop_agent.py` observes UI and executes allow-listed actions under an approved task; it is bounded to 24 steps/180 seconds, but lacks durable checkpoints and independent final verification for arbitrary UI.
- Remote: `remote/mobile.py` runs an authenticated local HTTP API and bounded job queues; `remote/home.py` wraps the server in TLS for direct use; `remote/relay_bridge.py` makes outbound requests to `relay_server/server.py`. `relay_protocol.py` uses AES-GCM envelopes and role-derived credentials. Android implements its own matching transport in `RelayTransport.java` and `RelayCrypto.java`.
- `android/` is a Java/Kotlin Android companion with foreground chat, file and desktop screens, pairing, audio capture and Android TTS, plus optional bundled voice preparation. `browser_extension/` is an optional Chromium Manifest V3 bridge to the loopback `browser_bridge/server.py`. Firefox compatibility is not established.
- Build: one `.github/workflows/build-windows.yml` currently contains separate Windows and Android **jobs**, not independent workflows. Android Gradle uses SDK 35, JDK 17 target and versionName 1.8.10/versionCode 11; Python package is 6.0.0.dev0 and desktop runtime identifies 6.0.0-dev. Historical 6.0 release notes describe an older Android version and must not override build files.

## Evidence and limits

On the current Linux workspace before this audit, Python suite: 497 passed / 8 skipped (before the last targeted DB fix); subsequent affected tests: 75 passed. Android JDK 17 Gradle `testDebugUnitTest` and `assembleDebug`: successful, 33 unit tests, local debug APK generated. These are local results, not GitHub Actions results. No Windows executable, physical phone, external network test, real account action, latency, or 4 GB device measurement has been verified here.

The project contains versioned patches, setup scripts, historical APKs, outdated README and third-party notices. Do not delete them without dependency and migration review. Bundled voice assets are downloaded at build time and are generated, not source changes; upstream revision and integrity are not pinned in the existing script.

## Stage A update

The working branch now has separate Windows and Android workflows, a loopback browser-origin mitigation, verified downloaded voice assets, and the previously developed task/file and memory corrections. On 2026-11-05, after those changes, `PYTHONPATH=src python -m pytest -q tests --import-mode=importlib` completed **504 passed, 8 skipped, 1 deprecation warning** on Linux. Local static syntax and workflow YAML parsing succeeded. Android rebuilt after voice changes is tracked separately in the test report; these checks do not certify Windows, actual browsers, physical phones or hosted CI.

Android stage-A recheck on JDK 17 and SDK 35: `:app:testDebugUnitTest :app:lintDebug :app:assembleDebug` succeeded; lint reported 0 errors and 21 warnings. APK is debug-signed with versionName 1.8.10/versionCode 11; see `TEST_REPORT.md` for exact scope.
