# Third-party Smart Agent component

Your Assistant Agent v1.6 includes a deliberately small tool-contract adapter inspired by the **smolagents** project from Hugging Face. The full smolagents runtime is not bundled, which keeps the desktop build lighter and avoids code-executing agent features.

- Project: `huggingface/smolagents`
- License: Apache License 2.0
- Purpose in this project: typed/validated allow-listed tools for Smart Agent actions.
- Integration style: small local adapter; no full smolagents runtime dependency.

This application does not enable arbitrary local CodeAgent execution. External actions remain constrained to explicit application tools and can require user approval.

The full Apache-2.0 license and upstream notices remain available from the upstream project and must be preserved when required by the license.
