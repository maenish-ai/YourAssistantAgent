# Offline voice component notices

Your Assistant Agent v2.2.0 may package the following local/offline voice components:

- **whisper.cpp** runtime from `ggml-org/whisper.cpp` and the multilingual `ggml-base.bin` Whisper model from `ggerganov/whisper.cpp`.
- **Piper** Windows runtime from the archived `rhasspy/piper` project.
- **Piper ar_JO Kareem (medium)** voice from `rhasspy/piper-voices` for Jordanian Arabic output.
- Python package **sounddevice** for local microphone capture.

No cloud audio service is required by the built-in local voice pipeline. See each upstream project/model for its applicable license and model/dataset terms.
