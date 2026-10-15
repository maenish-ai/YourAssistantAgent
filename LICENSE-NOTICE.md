# Third-party notices

The source ZIP does not include the large Hammer GGUF or llama.cpp binary. The Windows build workflow downloads them from upstream and verifies the configured Hammer SHA256 before packaging.

- **Hammer 2.1 0.5B**: `MadeAgents/Hammer2.1-0.5b` — repository declares **CC BY-NC 4.0**.
- GGUF used: `Melvin56/Hammer2.1-0.5b-GGUF`, `hammer2.1-0.5b-Q4_K_M.gguf` — repository declares **CC BY-NC 4.0**.
- **llama.cpp**: see `ggml-org/llama.cpp` upstream license/notices.
- Tool-contract adapter concepts from **Hugging Face smolagents**, Apache-2.0; see `THIRD_PARTY_SMOLAGENTS.md`.
- `pystray` and Pillow are used only for optional Windows tray UI; preserve their upstream licenses when redistributing.

The packaged v2.0.0 build is intended for personal/non-commercial use because of the Hammer model license.
