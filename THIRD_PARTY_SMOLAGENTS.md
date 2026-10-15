# Third-party Smart Agent design notice

Your Assistant Agent v2.0.0 keeps a deliberately small local tool-contract adapter inspired by **Hugging Face smolagents**. The full smolagents runtime is not bundled; this keeps the desktop build light and avoids enabling arbitrary code-executing agents.

- Project: `huggingface/smolagents`
- License: Apache License 2.0
- Purpose here: typed, validated, allow-listed tool contracts.
- Arbitrary local `CodeAgent` execution is not enabled.

See `licenses/Apache-2.0-smolagents.txt` for the included license text.
