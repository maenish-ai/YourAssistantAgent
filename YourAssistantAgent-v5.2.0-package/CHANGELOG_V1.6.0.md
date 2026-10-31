# v1.6.0 — Smart Agent Chat Shell

- Redesigned the desktop interface into a compact ChatGPT-like shell with a left sidebar.
- Added separate conversation sessions and a New Chat button.
- Kept Settings, Activity and Advanced one click away without cluttering Chat.
- Integrated a lightweight vendored tool-contract layer based on Hugging Face `smolagents` under Apache-2.0.
- Kept arbitrary CodeAgent/Python execution disabled; only application allow-listed tools can run.
- Added Smart Agent preview/approval/cancel/follow-up-edit flow.
- Added natural Facebook campaign parsing and matching-group counts before approval.
- Restored on-demand Facebook login/session/group-discovery automation without launching a browser at startup.
- Added a lightweight background scheduler for saved Facebook Smart Agent rules.
- Preserved Pending Approval as a successful Facebook submission state.
- Preserved normal conversation: greetings such as "كيف حالك؟" remain chat and can answer instantly.
- Preserved 4 GB RAM lazy loading, one-model-at-a-time behavior and resilient llama.cpp retry.
- Kept the original branding and single GitHub Actions workflow.
