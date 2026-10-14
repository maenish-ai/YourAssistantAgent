# Changelog

## 0.7.1
- Fixed Facebook group discovery so the Discover button records queued/running/completed/failed states.
- Discovery now scans Facebook **Groups you've joined / Your groups** first, then falls back to the Groups feed.
- Improved group-link parsing for current Facebook desktop layouts.
- Added a visible discovery status in the Facebook Groups tab and a clear zero-groups result.
- Discovery closes only the agent automation browser context when finished, releasing the dedicated profile cleanly.

## 0.7.0
- Added Smart Agent natural-language Facebook campaign rules.
- Added daily/weekday scheduling, post rotation, post offsets, and no-repeat history.
- Added discovery of Facebook groups visible to the connected profile.
- Added native Share -> Share to a group workflow for Smart Agent rules.
- Added Telegram Remote with authorized user ID, DPAPI-protected bot token, long polling, and confirmations for sensitive actions.
- Added Smart Queue, share history, dashboard status, audit events, Arabic/English UI strings, and tests.
- Fixed duplicate manual-login command dispatch in the UI.
- Updated installer/package version to 0.7.0.

## 0.6.4
- Manual Facebook login through the selected installed browser and saved-session verification.
