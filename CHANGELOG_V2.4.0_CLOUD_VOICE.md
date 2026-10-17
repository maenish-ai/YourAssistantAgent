# Your Assistant Agent v2.4 — Cloud Voice

- Added cloud-first Arabic voice mode with a live microphone waveform.
- Speech-to-text now uses Groq `whisper-large-v3` with Arabic forced and an Arabic/Jordanian context prompt.
- Arabic speech output now uses Groq Orpheus `canopylabs/orpheus-arabic-saudi` with the female `noura` voice.
- Added continuous voice conversation loop: listen -> understand -> answer -> speak -> listen again until stopped.
- Added cancellation and hard timeouts so voice/network work stays off the Tk UI thread.
- Added zero-download Windows SAPI fallback if cloud TTS is temporarily unavailable.
- Facebook status/check phrases now deterministically call `verify_facebook_connection` instead of opening login.
- Removed visible stale Qwen/local-brain wording from the chat UI at runtime.
- Removed Piper and local voice model payloads from Windows builds to reduce installer size.
