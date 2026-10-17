# Third-party notices

The source repository does not contain the large local model/runtime payloads. The Windows build workflow downloads pinned upstream artifacts and verifies configured model hashes before packaging.

- **Qwen3 1.7B**: `Qwen/Qwen3-1.7B`; GGUF used by the Windows build: `ggml-org/Qwen3-1.7B-GGUF`, file `Qwen3-1.7B-Q4_K_M.gguf` — declared **Apache-2.0**.
- **llama.cpp**: local model runtime from `ggml-org/llama.cpp`; preserve its upstream notices/license.
- **whisper.cpp** and multilingual Whisper base model: from `ggml-org/whisper.cpp` / `ggerganov/whisper.cpp`; preserve upstream notices/license.
- **Piper** runtime and **ar_JO Kareem** voice: from `rhasspy/piper` and `rhasspy/piper-voices`; preserve upstream runtime, voice-model, and dataset notices/terms.
- Tool-contract adapter concepts from **Hugging Face smolagents**, Apache-2.0; see `THIRD_PARTY_SMOLAGENTS.md`.
- `sounddevice`, `pystray`, and Pillow are used by optional desktop/audio UI paths; preserve their upstream licenses when redistributing.

See `THIRD_PARTY_QWEN.md` and `THIRD_PARTY_VOICE.md` for the packaged AI/voice sources.
