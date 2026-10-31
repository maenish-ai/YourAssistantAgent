# v2.5 Fast / Live Voice – cumulative patch after v2.3

- Added two voice modes: text dictation (does not send) and turn-based Live Conversation (automatically listens again after speaking).
- Live transcription uses Groq whisper-large-v3-turbo; dictation uses whisper-large-v3. Both specify Arabic and a Levantine hint.
- Noura female Arabic voice remains the default via Groq Orpheus, with one short request per Live reply and an interruptible Windows fallback.
- Removed unsupported Orpheus `speed` parameter; hardened network timeouts and cancel behavior.
- Streams GPT-OSS tool-compatible chat tokens to an ephemeral in-chat preview; uses `reasoning_effort=low` on interactive turns.
- Fast deterministic Facebook paths for open, check, and refresh; other requests still use normal tools and approval.
- Facebook extension Fast Refresh scans a bounded number of times in a temporary tab and closes **only** that temporary tab.
- No paid services, new speech models on disk, or API key bundled.

## Caveats
- Turn-based auto-listen, **not** full-duplex / acoustic echo-cancelled ChatGPT Live; pressing mic stops the voice session, press again to restart.
- Initial latency still depends on microphone, network, account limits, Facebook loading, and cloud capacity. Streaming speeds up first visible output, not necessarily the entire turn.
- Fast Refresh may return fewer groups than a deep crawl; it preserves older saved groups and reports the count.
- If Groq's free quota is exceeded, a free-plan error/fallback is shown; no billing is initiated.
- The extension needs to be reloaded in Edge after installing this build so its new JavaScript is active.
