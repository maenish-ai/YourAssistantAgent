# Your Assistant Agent v2.6 — Fix Stuck Requests / Voice / Facebook / GitHub Desktop

This patch is cumulative on the user's installed GroqCloud v2.3 **source repository**: it includes the v2.4/v2.5 source patch files as well as v2.6 changes. It is not a Windows installer.

## Changes

- Cloud request cancellation: each chat turn has a unique identity; clicking Stop or submitting a different command invalidates the previous turn and discards all stale responses and streamed previews. The old Qwen Stop handler is rewired to actually cancel cloud operations.
- Tool execution cancellation: cloud processing checks the cancel flag before each new tool operation, and before and after the model request; in-flight network calls may require a timeout to fully exit.
- Old campaign approvals: unrelated new commands do not inherit a pending Facebook sharing approval, and Stop clears pending actions. Edits to a pending plan and explicit approval/cancellation are still handled normally.
- Facebook: ambiguous *page-editing* tasks (e.g. create highlights/pin a page post) ask for clarification instead of guessing `/photos`. Model can no longer select the manual-login opener without an explicit direct user action. Group refresh and verification tool calls use the v2.5 fast browser-extension paths.
- Live voice: independent STT and TTS service instances and cancel states, visible microphone/STT errors and cloud TTS failure reports, 6-second initial speech timeout, shorter recording cap, and shorter live STT network timeout. Reduces silent "live mode does nothing" behaviour but requires Windows microphone and live Groq testing.
- Cloud model response caps: voice text replies are bounded and streamed, less time waiting before Noura is spoken. Noura still depends on Groq free-tier availability; no new payment or credit-card requirement is introduced.
- GitHub Desktop: dedicated chat button and direct Arabic/English commands open an *already installed* GitHub Desktop. A second read-only Git status button inspects the Desktop\YourAssistantAgent repository without pushing. This does **not** authorize the assistant to access GitHub or push code automatically. Sign-in and repository permissions remain under user control.
- Installer metadata now identifies version 2.6.0 and retains the original AppId for in-place upgrades.

## Limitations

- This patch has not been tested against a real Windows microphone, Facebook account, or Groq key in this environment; a built and installed Windows test is needed.
- Stopping the UI prevents new tool actions and stale replies but cannot instantly undo an already-started Facebook action or guarantee immediate interruption of a stalled external network request.
- The current CloudVoice conversational mode is turn-based, not full-duplex ChatGPT Live. It is intentionally minimal to avoid local large models and paid infrastructure.
- Voice free limits and Groq API availability are controlled by Groq, not by this patch.
