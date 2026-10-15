# Your Assistant Agent v1.4.2

GitHub Actions reliability hotfix:

- Only one active workflow is included in the full project: `.github/workflows/build-windows.yml`.
- The build tests only the current v1.4 Lite code, so stale tests from older repository versions cannot fail the new Lite build.
- The llama.cpp Windows x64 CPU runtime discovery/fallback remains enabled.
- Workflow concurrency cancels superseded runs on the same branch.
- Installer and package version updated to 1.4.2.

Important for an existing GitHub repository:
GitHub web uploads replace/add files but do not delete old files that are absent from the ZIP. If `.github/workflows/windows-build.yml` still exists in the repository, delete it once. After that, future pushes use only `Build Windows Setup`.
