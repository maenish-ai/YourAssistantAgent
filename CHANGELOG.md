# Changelog

## 1.7.0
- Single visible Hammer 2.1 Smart Agent.
- Removed visible Arabic/General agent chooser.
- Added Hammer tool routing for Facebook tasks and ordinary conversation.
- Added bilingual Chat / Status / Settings / Advanced shell.
- Added live Facebook progress timeline.
- Installer now downloads one verified Hammer Q4_K_M model only.

## 1.6.0
- New ChatGPT-like sidebar/chat interface with recent conversations.
- Integrated a safe smolagents-based Smart Agent tool layer.
- Added preview, approval, cancellation and natural follow-up edits for Facebook work instructions.
- Added real on-demand Facebook connection/group discovery and lightweight scheduled rule execution.
- Normal conversation remains chat; common Arabic greetings answer instantly.
- Preserved low-memory local AI behavior, branding, signing readiness and one workflow.

## 1.5.0
- Restored Chat / Activity / Settings / Advanced application shell.
- Added resilient local-AI retry and persistent diagnostics.
- Tuned low-memory fallback for 4 GB laptops.
- Kept one GitHub Actions workflow and existing startup/branding/signing fixes.

## 1.4.3
- Fixed packaged startup import crash.
- Restored full original branding.
- Added Windows metadata and optional Authenticode signing.
- Added packaged EXE startup smoke test.
- Added best-effort automatic legacy workflow cleanup.

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