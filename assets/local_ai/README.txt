Your Assistant Agent — Dual Local AI assets

Source repository intentionally does not store the large GGUF model files or llama.cpp binaries.
During Windows build, scripts/prepare_local_ai.ps1 downloads and SHA256-verifies:

1) General brain: Qwen3-0.6B-Q4_0.gguf
2) Arabic brain: RightNow-Arabic-0.5B-Turbo-q4_k_m.gguf
3) llama.cpp Windows CPU runtime

Runtime policy for low-memory PCs:
- Auto: Arabic message -> RightNow Arabic 0.5B; other text -> Qwen3 0.6B.
- Only one model is loaded in RAM at a time.
- General and Arabic modes can be forced from Smart Agent settings.
- A custom local GGUF path overrides the bundled model selector.

No paid API token is required for bundled Local AI.
