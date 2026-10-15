# Your Assistant Agent v1.4.3 — Startup, Branding & Trust Fix

- Fixed packaged startup crash: `attempted relative import with no known parent package`.
- Added a stable absolute-import launcher and packaged EXE self-test.
- Restored the approved purple/blue robot-orbit brand throughout the app.
- Restored branded EXE icon, taskbar icon, splash, agent picker, chat header, installer wizard, shortcuts and uninstall entry.
- Added Windows EXE and installer version/company/product metadata.
- Kept the lightweight one-folder, no-UPX build to reduce false-positive risk.
- Added optional Authenticode signing steps for both app EXE and Setup when a real PFX certificate is supplied via GitHub Secrets.
- Added a first-run best-effort cleanup job that removes the legacy duplicate `windows-build.yml` workflow from the repository using `GITHUB_TOKEN` with `contents: write`; failure to clean does not block the build.
- Added CI packaged startup smoke test before publishing the installer.
