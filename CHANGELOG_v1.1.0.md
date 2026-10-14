# Your Assistant Agent v1.1.0 — Local Employee AI

## Major upgrade
- Added a free, private Local AI brain bundled into the Windows installer.
- Local model: Qwen3-0.6B GGUF, running through llama.cpp on `127.0.0.1` only.
- No API token, paid subscription, or internet connection is required after installation for Local AI understanding.
- Added provider abstraction: Local AI by default, optional OpenAI-compatible external endpoint, and deterministic safe fallback.
- The external provider is optional. If it fails, the bundled Local AI is attempted before the parser fallback.

## Conversation intelligence
- The Smart Agent now sends natural Arabic/English, recent conversation context, current preview context, date/time, and defaults to the local language model.
- Supports colloquial Jordanian/Levantine Arabic, mixed Arabic/English, short follow-up edits, and voice-dictation style text.
- The AI classifies non-campaign messages such as status, rules, GitHub questions, Telegram help, and ordinary conversation instead of forcing every sentence into a campaign.
- A filtered request may never silently become “all groups”. Ambiguity causes one clarification question.
- Conversation context is kept for the desktop Smart Agent session and persisted locally between restarts until cleared/approved.
- Telegram free-form messages use the same brain and can answer status/rules questions without slash commands.

## Facebook workflow safety
- Admin-review submissions remain `Pending Approval` / `Submitted`, not `Failed`.
- Pending approval counts as already sent for duplicate prevention.
- Existing Facebook discovery, native Share -> Share to a group, Smart Queue, audit, retries, and checkpoint-stop behavior remain intact.

## UI
- Added a brighter modern Qt theme using only built-in PySide6 styling.
- Modern rounded tabs/cards, vibrant purple/blue accents, clearer tables, focus states, and improved form controls.
- AI settings now show Local AI vs optional External AI clearly.
- A custom GGUF path can be selected later for a stronger local model without changing the program architecture.

## Build and packaging
- GitHub Actions now downloads pinned llama.cpp + Qwen model assets, validates SHA-256, and packages them in the Windows Setup.
- Large AI binaries are not committed to Git, avoiding GitHub’s file-size limits.
- The Windows build remains Setup-only.
