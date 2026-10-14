# Changelog

## 1.2.0 — Dual Local Brain
- Added RightNow-Arabic-0.5B-Turbo Q4_K_M alongside Qwen3-0.6B.
- Added Auto / General / Arabic local brain selection.
- Auto routes Arabic text to the Arabic model and other text to Qwen.
- Only one llama.cpp model is resident at a time for 4 GB RAM safety.
- Auto mode falls back to the alternate bundled model on hard local-AI failure.
- GitHub Actions downloads and SHA256-verifies both GGUF files before packaging.
- Version updated to 1.2.0.

## 1.1.0 — Local Employee AI
- Added bundled free Local AI using Qwen3-0.6B GGUF + llama.cpp.
- Local AI is the default understanding engine and needs no API token or paid subscription.
- Added optional generic OpenAI-compatible external provider with Local AI fallback.
- Added contextual natural conversation, follow-up edits, non-campaign intent classification, and Telegram natural-language responses.
- Added strict audience safety: a filtered request cannot silently become all groups.
- Persisted recent desktop Smart Agent conversation context locally until approved/cleared.
- Added modern bright purple/blue Qt theme with rounded cards, tabs, controls, and tables.
- GitHub Actions now downloads pinned Local AI runtime/model files, validates SHA-256, and bundles them into Windows Setup.
- Large AI binaries remain outside Git and are fetched only during Windows build.
- Version updated to 1.1.0.

## 1.0.1
- Fixed missing GitHub deployment module in packaged startup build.
- Added packaging preflight imports.

## 1.0.0
- Added Employee Mode AI brain, contextual planning, Pending Approval handling, and moderation-state tracking.

## 0.9.0
- Improved generic natural-language group filter extraction.
- Added GitHub Deployment UI and safe branch/test/commit/push workflow.

## 0.8.0
- Added rule Edit/Delete/Cancel, Telegram remote enhancements, Wake/Sleep and Wake-on-LAN support.

## 0.7.1
- Fixed Facebook group discovery, state reporting, and current Groups layout parsing.

## 0.7.0
- Added Smart Agent rules, Facebook group discovery, native Share -> Share to a group, Telegram Remote, Smart Queue and share history.

## 0.6.x
- Added manual Facebook login through selected installed browser, browser discovery, bilingual installer, Windows update process management, and Setup-only GitHub build.
