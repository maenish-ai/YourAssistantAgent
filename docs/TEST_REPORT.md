# Test report — development branch

Date 2026-11-05; base `fce07d0` plus this branch's changes. These are local results, not GitHub Actions results.

| Check | Result | Evidence / scope |
|---|---|---|
| Full Python suite | Passed | `PYTHONPATH=src python -m pytest -q tests --import-mode=importlib`: **504 passed, 8 skipped, 1 warning**; Linux, mocks and local fixtures included. |
| Bridge/asset/build targeted tests | Passed | 18 passed for bridge transport, mocked extension worker, build separation and asset verification. Does not test an installed real extension. |
| JavaScript syntax | Passed | `node --check browser_extension/background.js`. |
| Workflow syntax | Passed | Both YAML files parsed using PyYAML BaseLoader and contain separate `android` and `build` jobs; GitHub Actions execution not performed. |
| Android Gradle local | Passed | JDK 17, SDK 35: `:app:testDebugUnitTest :app:lintDebug :app:assembleDebug`. 33 JVM/Robolectric tests, lint **0 errors / 21 warnings**, build successful. Some tasks were up to date from the preceding verified local build. |
| Android APK inspection | Passed | `aapt dump badging`: package `ai.maenish.yourassistant`, versionName 1.8.10, versionCode 11. `apksigner verify`: Android Debug signing certificate, not production-signed. Not installed or exercised on a physical phone. |
| Windows build / startup / runtime | Not tested | Environment is Linux; no Windows EXE or installer created, no Windows device. |
| Relay reconnect and transport | Passed / partial | After adding backoff: `tests/test_relay.py tests/test_mobile_server.py tests/test_home_hosting.py`: **36 passed, 3 skipped**. Includes local broker restart/replay tests; does not verify external networks. |
| Device/network/account/performance acceptance | Not tested | No physical Android, Windows host, external relay, real social/GitHub account actions or target 4 GB performance measurements. See `FEATURE_GAP_ANALYSIS.md` for all 15 acceptance scenarios. |

A successful tool call or mock test is not proof of task completion on a real account. No actual GitHub Actions run or release has been triggered from this branch.
