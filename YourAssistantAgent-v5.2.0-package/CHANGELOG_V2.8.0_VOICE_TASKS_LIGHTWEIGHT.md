# Your Assistant Agent v2.8.0 — Voice, Tasks and Lightweight Background

## What changed

- **Microphone selection:** Choose an input device in the chat, save it in normal application settings, and run a private four-second WAV recording/playback test before involving Groq.
- **Correct audio sampling:** Capture at the microphone device's actual native sampling rate (e.g., 44.1 or 48 kHz) and write matching WAV metadata. Groq Whisper supports WAV uploads; no large local voice model or resampler was added.
- **Fewer false "I can't hear you" errors:** Keep early speech samples and forward quiet-but-real recordings to Whisper instead of rejecting them solely via an aggressive local RMS threshold.
- **No silent mic failure:** Missing devices, unplugged saved device and silent input now have more diagnostic messages. Mic streams only open when requested and are closed on completion or cancellation.
- **Delete tasks:** Delete via the table Delete/Backspace keys, right-click menu, the existing Delete button, or a new Delete button on every card. Ask confirmation first. For currently running jobs: disable future schedules, request cancellation, then remove only after the worker stops.
- **Background resource reduction:** Cloud inference remains on Groq. Hidden windows poll status less often; the old idle handler no longer schedules duplicate backup timers; no new permanent background threads or heavy speech packages were added.
- **Windows installer and Actions:** v2.8.0 metadata, updated packaging imports, and regression tests.

## Requirements / limitations

- The update is a **source overlay** for your existing full GitHub repository, not a self-contained installer.
- The microphone chooser runs on the Windows machine with the actual hardware. Automated tests used simulated devices; real Windows microphone and Groq voice roundtrip still require end-to-end validation after installation.
- Device names may change after reinstallation/unplugging; select the microphone again if needed.
- A task already executing a remote/browser operation may take time to honor cancellation. Never delete its database row before its worker stops.
- No changes to key storage, payment plan or account permissions. Groq free-tier limits still apply.
