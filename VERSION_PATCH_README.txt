YourAssistantAgent 6.0.0-dev — VERSION CONSISTENCY PATCH ONLY

This patch aligns the Windows development version and build artifact labels.
It DOES NOT implement or certify all 6.0 features, nor fix an unknown GitHub Actions failure.
The Android companion stays on its independent 1.7.0 version; no APK is included.

Extract these files into the ROOT of the repository, preserving paths.
Commit and push; check Actions logs. If Actions still fails, provide the FAILED job log.

Files changed:
pyproject.toml
src/yaa_lite/__init__.py
installer/YourAssistantAgent.iss
version_info.txt
.github/workflows/build-windows.yml
tests/test_text_first_v300.py
README.md
