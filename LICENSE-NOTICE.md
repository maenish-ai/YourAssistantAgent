# Third-party notices

This source package does not include the large AI model binary or llama.cpp binary. The Windows build workflow downloads them from their upstream projects and verifies the configured SHA256 before packaging.

- **Hammer 2.1 0.5B** original model: `MadeAgents/Hammer2.1-0.5b` — repository declares **CC BY-NC 4.0**.
- GGUF quantization used by this build: `Melvin56/Hammer2.1-0.5b-GGUF`, `hammer2.1-0.5b-Q4_K_M.gguf` — repository declares **CC BY-NC 4.0**.
- **llama.cpp**: see `ggml-org/llama.cpp` upstream license/notices.
- The lightweight tool-contract adapter remains based on concepts from **Hugging Face smolagents**, Apache-2.0; see `THIRD_PARTY_SMOLAGENTS.md` and `licenses/Apache-2.0-smolagents.txt`.

This v1.7 build is intended for personal/non-commercial use because of the Hammer model license. Review and satisfy every upstream license before redistribution or commercial use.
