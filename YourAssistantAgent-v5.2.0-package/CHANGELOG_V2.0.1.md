# Your Assistant Agent v2.0.1 — Hammer response hotfix

- Fixed the main Hammer non-response/ConnectionReset failure path.
- Hammer tool calls now use Hammer 2.1's native JSON-list prompt rendered by the app and llama.cpp raw `/completion` endpoint.
- Removed dependency on llama.cpp server-side OpenAI tool parsing for Hammer.
- Ordinary chat also goes through Hammer's `respond` tool; there is still no secondary chat model.
- Kept two automatic restart attempts, with low-memory and ultra-safe modes.
- Added richer local-AI log details for HTTP failures and server exits.
- Pinned the Windows llama.cpp runtime build in GitHub Actions instead of following changing pre-releases.
- First-run Optional Services now has an explicit Skip button; Google Drive OAuth remains optional and does not block chat.
