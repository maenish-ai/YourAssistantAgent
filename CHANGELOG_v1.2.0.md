# Your Assistant Agent v1.2.0 — Dual Local Brain

## What changed

- Added **RightNow-Arabic-0.5B-Turbo Q4_K_M** as a bundled Arabic local model.
- Kept **Qwen3-0.6B Q4_0** as the bundled general local model.
- Added Local Brain modes: **Auto / General / Arabic**.
- Auto mode routes Arabic messages to the Arabic model and other text to Qwen.
- Only one llama.cpp model is loaded at a time to protect low-memory laptops (including 4 GB RAM machines).
- If Auto mode hits a hard local-AI failure, it can try the alternate bundled model before falling back to the deterministic parser.
- GitHub Actions now downloads and SHA256-verifies both GGUF models before packaging the Windows installer.
- Existing Facebook, Pending Approval, Telegram, GitHub Deployment, Wake/Sleep and safety behavior is retained.

## Bundled model files during Windows build

- `Qwen3-0.6B-Q4_0.gguf`
- `RightNow-Arabic-0.5B-Turbo-q4_k_m.gguf`

Large model files remain outside Git. The build script downloads them during GitHub Actions and includes them in the final Windows Setup.
