# Your Assistant Agent v1.4.1

- Fixed GitHub Actions failure while downloading llama.cpp Windows x64 CPU runtime.
- The build now searches recent llama.cpp releases, including prerelease/build releases, instead of assuming `releases/latest` contains binaries.
- Added a pinned runtime fallback for resilience.
- Added explicit runtime staging validation before tests/build.
- Added workflow concurrency to cancel superseded builds on the same branch.
- Project contains one active workflow: `.github/workflows/build-windows.yml`.
- Added one-time cleanup note for the legacy `.github/workflows/windows-build.yml` still present in the existing GitHub repository.
- Bumped app/installer version to 1.4.1.
