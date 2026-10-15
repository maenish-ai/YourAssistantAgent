# Changelog

## 1.4.2
- Fixed GitHub Actions test failure caused by legacy v1.3 test files remaining in an existing repository.
- The active workflow now runs only the five v1.4 Lite tests used by this build.
- Full source package contains exactly one active workflow file: `.github/workflows/build-windows.yml`.
- Retains the llama.cpp Windows runtime fix from v1.4.1.
- Bumped app/installer version to 1.4.2.

## 1.4.1
- Fixed llama.cpp Windows runtime discovery in GitHub Actions.
- Added recent-release scan + pinned fallback.
- Added workflow concurrency and runtime verification.
- Bumped version to 1.4.1.

## 1.4.0
- New pre-chat Arabic/General agent picker.
- Lazy local-AI startup.
- One model process at a time.
- Tk/ttk lightweight shell replacing heavier UI dependencies.
- Background AI worker and queue-based GUI updates.
- Enter-to-send and Shift+Enter newline.
- Fast greeting path.
- Conservative 4 GB RAM defaults.
- Stop-AI memory release.
- Encrypted backup core retained.
