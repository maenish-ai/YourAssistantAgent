# Your Assistant Agent v2.0.0 — Hammer OS Foundation

## Hammer as the only brain
- Removed hidden fast greeting replies: every user message now reaches Hammer.
- Removed semantic keyword routing from the chat layer. Hammer selects the application tool; the app remains the permission boundary.
- Initial model attempt plus two automatic safer restarts.
- Added Eco / Balanced / Performance handling and automatic idle unload.

## New application shell
- ChatGPT-style left rail: Home, Chat, Status, Facebook, Tasks, Backup, Settings.
- Arabic-only or English-only UI; the old mixed/bilingual runtime UI is removed.
- First-run setup wizard and lock/unlock flow.
- Session search, rename, pin, archive, private-chat and memory-per-chat controls.
- Global search foundation across chats, tasks, groups and memory.

## Security and backup
- Password modes: every launch / once per Windows session / none.
- Separate Recovery Key; raw password/recovery key are never stored.
- AES-GCM encrypted backup format with portable password/recovery key envelope for new-device restore.
- Google Drive OAuth 2.0 + PKCE client using `appDataFolder`.
- Local backup history, Drive version listing and Drive restore foundation.
- Facebook credential/session sync remains opt-in and is excluded by default.

## Facebook and browser
- New Facebook workspace page and live execution status.
- Browser extension bridge on localhost for the user's normal browser.
- Extension-first manual Facebook login with managed-browser fallback.
- Automatic startup check no longer opens a managed browser merely to test Facebook.
- Existing Facebook scheduler/group sharing engine retained with pause/resume/stop progress controls.

## Voice and Windows integration
- Lazy Windows System.Speech one-shot STT/TTS foundation.
- System tray support through optional `pystray`.
- Start-with-Windows registry mode support.

## Packaging
- Version 2.0.0 metadata and installer output.
- Browser extension packaged with the application.
- Single GitHub Actions workflow.
- Expanded v2 test suite.

## Known staged areas
Telegram/GitHub full remote actions, skill marketplace/builder, full browser-extension migration of all Facebook DOM actions, wake-word continuous listening, advanced report exports and automatic multi-device conflict merge are architectural targets/settings in this foundation but are not all production-complete yet.

- Hammer context defaults to 2048 tokens (Eco 1024; retry 1536/1024) so the tool schema and conversation fit reliably while remaining lightweight on a 0.5B model.
