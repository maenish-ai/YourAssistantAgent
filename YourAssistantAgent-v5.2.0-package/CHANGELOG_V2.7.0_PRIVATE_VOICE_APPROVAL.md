# Your Assistant Agent v2.7 — Private Approval + Arabic Voice Comparison

**Cumulative Windows source overlay:** includes v2.4, v2.5 and v2.6 patches for existing GroqCloud-based `maenish-ai/YourAssistantAgent` repo. Upload to the **same repository root**, not into an extra folder.

## Implemented and ready for the Windows CI build

- **Explicit human-in-the-loop actions:** the chat shows a full preview with `✅ موافق` and `✖ إلغاء` for the existing Facebook campaign publishing and scheduled task-run actions. A spoken/typed **«نعم» alone does not authorize** execution. The button authorizes one matching tool+arguments+summary+creation timestamp, only when the action was prepared within 15 minutes, and the confirmation token is consumed once. Other new/unknown tools are **denied by default** until they are reviewed and classified; no arbitrary command execution.
- Keeps v2.6 cloud request cancellation, old-turn isolation, faster Facebook navigation, GitHub Desktop shortcut and reported voice errors.
- **Official/default female Arabic voice:** `noura`, Groq `canopylabs/orpheus-arabic-saudi`.
- **Experimental comparison voice:** `ar-JO-SanaNeural`, provided by `edge-tts`, an unofficial open-source client for Microsoft's online speech service. The preview is a short non-sensitive test text; selecting Sana as the assistant's regular speaking voice requires an explicit warning/opt-in confirmation. It does **not** run or deploy on Groq servers; it connects separately to Microsoft.
- Independent provider selection persisted as a tiny config JSON under the user's local config directory (no API keys). Default is Noura.
- Redacts common secret-token patterns before sending assistant text to either speech provider. **Pattern matching is not an absolute guarantee**; do not ask any cloud TTS to read account passwords or sensitive secrets.
- No local TTS model or high-compute speech engine downloaded. Build adds the small Python `edge-tts` client, and includes its third-party license notice.
- Installer and file version bumped to `2.7.0`. CI builds a Windows Setup executable and a SHA256 checksum.

## Intentional boundaries

- This ZIP is a **Windows source-code overlay**, **not an APK and not a complete standalone repository**. It only builds Windows when uploaded over your existing complete GitHub repository. It does not add remote phone control or WhatsApp account access.
- The prior campaign preview and execution logic is reused. New future actions (GitHub pushes, file deletion, WhatsApp sends) **are not enabled** by this patch. They require implementing real connectors plus a separate per-action approval flow; this release never silently authorizes them.
- GitHub Desktop shortcut ≠ authorization to push to GitHub. Existing local `GROQ_API_KEY` stays on your PC.
- `edge-tts` is unofficial and its availability, cost conditions, ToS, privacy terms and quality may change. We have no guarantee that Sana works in a particular network or indefinitely for free.
- Groq Free Plan limits apply; no upgrades or payment are initiated by the app.
- This environment cannot run an actual Windows installer, authenticate the user's Groq key, or test Edge/Facebook/microphones. **Use GitHub Actions results and then a real Windows smoke test** before relying on it with private accounts. A passing Python syntax/unit test is not proof of end-to-end function.

## Sources / license

- Groq Orpheus official docs: https://console.groq.com/docs/text-to-speech/orpheus
- Microsoft voice catalog: https://learn.microsoft.com/en-us/azure/ai-services/speech-service/language-support
- edge-tts source: https://github.com/rany2/edge-tts (LGPL-3.0 except one MIT component; see upstream LICENSE and THIRD_PARTY_EDGE_TTS.md).
