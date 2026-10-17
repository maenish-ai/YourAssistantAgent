# Your Assistant Agent v2.2.0 — Direct Personal Assistant

- Qwen3 1.7B remains the only shipped AI brain.
- Removed the synthetic `respond` tool from the primary assistant path. Ordinary conversation is now native Qwen chat text.
- Enabled llama.cpp Jinja chat templates (`--jinja`) and native OpenAI-compatible Qwen tool calls.
- Added a multi-step personal-agent loop for safe/read-only actions, with a five-step hard cap.
- Added Facebook login opener, connection verification, group refresh and structured group search tools.
- Added structured include/exclude filters for Facebook groups, including exact-name exclusions such as “الفحص التجارية”.
- Added current-chat Facebook group selection context so follow-ups like “اعتمدهم” can reuse the previous selection when chat memory is enabled.
- Added structured Facebook campaign drafting with deterministic preview and approval before publish/run.
- “Run now” Facebook campaigns are saved as one-off disabled rules after being handed to the background worker so they do not repeat unexpectedly.
- Kept offline Whisper -> Qwen -> Piper voice conversation from v2.1.
- Kept the v2.0.2 normal-browser Facebook group discovery compatibility layer.
