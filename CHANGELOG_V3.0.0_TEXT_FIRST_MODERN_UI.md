# Your Assistant Agent 3.0.0 — Text-first, lightweight, modern chat

This is a **source patch** to be merged into the existing full repository
`maenish-ai/YourAssistantAgent` at v2.9 or later. It is not a standalone app.

## Owner-requested behavior

- **No speech replies.** No Noura, Sana or Windows TTS is invoked from the new chat.
  Speech output controls are removed from the chat and replaced by text only.
  Legacy compatibility modules remain in source; do not use their voice UI.
- **Optional dictation only:** click `🎙 إملاء نص` to listen, and the Groq Whisper
  transcription appends *editable text* in the compose field. No auto-send.
  Click the button again to end dictation. Transcription appears after a phrase
  or a short capture interval, **not per individual word in true realtime**;
  Whisper transcription uses uploaded audio clips.
- No local speech model or new heavyweight AI engine. `edge-tts` is no longer
  collected/bundled by the current Windows spec.
- Cleaner, larger main text chat, compact controls and permanent GitHub Desktop
  / local Git status shortcuts. Settings shows microphone/dictation only instead
  of previous TTS configuration.
- Arabic display reshaping via tiny `arabic-reshaper` and `python-bidi` libraries.
  These are used only to paint messages, never to alter raw stored messages.
  Right-click chat to copy the last complete original assistant response.
- Each new request starts with **no old conversational turns**. A new command
  clears any previous pending-action preview; the only exception is the owner
  explicitly clicking the current approval button. This deliberately reduces
  conversational continuity to meet the owner's preference.
- A plain Facebook profile URL alone receives an immediate clarification request
  instead of browsing pages without a task.
- Normal conversation uses one direct Groq completion without the complex
  tool-selection pipeline. Commands that look like app/tool actions still use
  the existing allowlisted controller and approval system.
- The UI stops waiting after 50 seconds and ignores late replies. **Caution:**
  an already launched external action might continue; check its state before
  retrying a sensitive operation.
- Removed the 700ms repeated app-wide old-Qwen label replacement from `main.py`.
  Visible legacy labels are updated once when opening a section instead.

## Limitations, privacy, and testing

- The Groq free tier has usage limits; dictation sends microphone audio to Groq.
  Microphone input remains disabled until the user explicitly starts dictation.
- GitHub Desktop opens the user's own installed app. This is NOT automatic GitHub
  account authorization or arbitrary repository write permission.
- The text-first shell changes the Tk chat area, not the entire old settings and
  sidebar framework; parts of the old app still use existing ttk controls.
- UTF-8 source/text only. No `.env`, token or password is included.
- 50 targeted source/unit tests passed in the patch reconstruction workspace.
  A headless Tk smoke test completed; the full Windows CI build and physical
  audio device behavior have **not** been verified here.
- To avoid overload on an older laptop: install only after GitHub Actions passes;
  don't enable background tasks or auto-backup unless desired.
