# Your Assistant Agent v2.0.1 — Hammer OS Foundation

A lightweight Windows desktop assistant built around **one local AI brain: Hammer 2.1 0.5B**. The desktop app is the interface, state store, permission boundary and tool host; Hammer handles all conversation and decides when an allow-listed application tool should be used.

## Core v2 behavior

- **Hammer only**: greetings, casual chat and work commands all go through Hammer. There is no hidden Arabic/General fallback model and no hard-coded greeting reply path.
- **Resilient local runtime**: initial attempt + up to two automatic restarts (low-memory, then ultra-safe) with persistent `local_ai.log` diagnostics.
- **4 GB friendly**: one ~398 MB Q4 model, lazy loading, idle unload, Eco/Balanced/Performance modes, max 2 CPU threads and max 1024 context by default.
- **One-language UI**: first run asks for Arabic or English. Arabic mode is Arabic-only; English mode is English-only. The language can be changed later from Settings.
- **ChatGPT-like shell**: left navigation rail with Home, Chat, Status, Facebook, Tasks, Backup and Settings. Telegram/GitHub stay under Advanced until enabled.
- **Live status**: current Facebook task, progress bar, pause/resume/stop and a timestamped activity timeline.

## Security and backup

First run creates the app security layer. The user chooses whether a password is requested every launch, once per Windows session, or not at all. A separate **Recovery Key** wraps the same random master encryption key.

Backups use AES-GCM and are encrypted **before** Google Drive upload. v2 backup files include only encrypted key-wrapping metadata outside the ciphertext, so the original password or Recovery Key can unlock a backup on a new computer. Google Drive uses the official OAuth flow with `drive.appdata`; a real Desktop OAuth Client ID must be supplied by the user/package owner.

Facebook browser-profile/session material is excluded from backups by default. Credential syncing is opt-in per service.

## Normal-browser bridge

`browser_extension/` contains the optional browser bridge. It connects the user's **normal open browser** to the desktop app through localhost `127.0.0.1:8765`. The bridge has an allow-listed command channel for opening pages and interacting with the active tab.

In v2.0.1 the extension is the preferred path for opening Facebook/manual login and lightweight browser status work. The mature Facebook sharing engine still has a managed-browser fallback for operations that have not yet been migrated to the extension command channel. CAPTCHA and Facebook checkpoints are always manual.

## Facebook Smart Agent

Hammer exposes safe tools for:
- app/Facebook/backup status
- task listing
- group counting
- group discovery (approval-gated)
- preparing Facebook campaigns
- running saved Facebook rules (approval-gated)

The app never exposes arbitrary Python execution to Hammer. Publishing/external actions remain behind the approval boundary. Scheduled sharing keeps no-repeat checks and records published/pending/failed outcomes.

## Voice

The microphone button can use Windows' built-in **System.Speech** locally when local voice is enabled. TTS also uses installed Windows voices. Voice quality/available female voices therefore depend on Windows language/voice packs. Cloud voice, wake-word continuous listening and premium voice packs are represented in Settings but require optional skills/providers; they are not silently enabled.

## Features staged behind the v2 architecture

The UI/settings/data model now have foundations for Telegram, GitHub, Skills, proactive learning, advanced reports, multi-device conflict resolution and richer browser-extension automation. These are **not all production-complete in v2.0.1**. In particular, do not treat the current Telegram/GitHub connector placeholders or the browser extension as equivalent to a fully migrated production connector yet.

## Hammer model and license

- Original: `MadeAgents/Hammer2.1-0.5b`
- GGUF: `Melvin56/Hammer2.1-0.5b-GGUF` / `hammer2.1-0.5b-Q4_K_M.gguf`
- SHA256: `190676fe7ac430ac6680b32c216d4eb7413002e2af0c140b8280a0f74fcc6a4d`
- Declared model license: **CC BY-NC 4.0**

Because of the Hammer model license, this packaged build is intended for personal/non-commercial use unless the model is replaced or separately licensed.

## Build

Push the complete project to `main`. The single workflow `.github/workflows/build-windows.yml`:
1. installs dependencies,
2. runs the source self-test and all tests,
3. downloads and SHA-verifies Hammer,
4. downloads llama.cpp Windows CPU runtime,
5. builds the PyInstaller one-folder application,
6. smoke-tests the packaged EXE,
7. builds the Inno Setup installer,
8. optionally Authenticode-signs the EXE/Setup when signing secrets are configured,
9. uploads the Setup artifact and SHA256.


## v2.0.1 Hammer runtime note
Hammer requests are rendered with the model's native function-calling prompt and sent through llama.cpp raw completion. Google Drive OAuth is optional and unrelated to local chat.
