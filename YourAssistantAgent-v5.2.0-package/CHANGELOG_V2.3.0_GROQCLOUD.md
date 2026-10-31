# v2.3.0 GroqCloud migration patch

- GroqCloud `openai/gpt-oss-120b` becomes the primary reasoning/tool-calling brain.
- Existing desktop approval boundary and local Facebook tooling remain intact.
- Groq Whisper `whisper-large-v3-turbo` handles speech-to-text.
- Piper Arabic Jordanian TTS remains local.
- Windows build no longer downloads/packages Qwen GGUF, llama.cpp, or whisper.cpp.
- API key is never committed; runtime reads `GROQ_API_KEY` from the environment or local `.env`.
