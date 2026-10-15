# Your Assistant Agent v1.6.0

A lightweight Windows desktop assistant with a **ChatGPT-like compact interface**, local Arabic/General AI, and a controlled Smart Agent tool layer.

## What changed in v1.6

The application is now conversation-first:

- A left sidebar contains **New chat**, recent conversations, **Activity**, **Settings**, **Advanced**, and agent switching.
- The center is the chat. `Enter` sends; `Shift+Enter` adds a new line.
- Simple conversation such as **"كيف حالك؟"**, **"شو أخبارك؟"** and greetings works as normal chat. Common greetings answer instantly without loading the local model.
- Work instructions are routed through the **Smart Agent**. The agent creates a readable plan, counts matching saved Facebook groups, asks for approval, and accepts natural follow-up edits such as **"خليها الساعة 9"** before saving.
- Chat conversations are stored as separate sessions and shown in the sidebar.

## Smart Agent architecture

v1.6 uses a **lightweight vendored smolagents-compatible tool contract** derived from the Apache-2.0 Hugging Face project, while keeping execution restricted to explicit application tools. We intentionally do **not** expose `CodeAgent` or arbitrary Python execution on the user's computer.

Current allow-listed tools include:

- count saved Facebook groups by natural-language keyword;
- discover/refresh joined Facebook groups;
- read Facebook connection status;
- save an approved Facebook sharing schedule;
- run a saved Facebook rule now.

The local conversation model and Smart Agent are separate responsibilities:

1. **Conversation model** — Arabic/General natural conversation and explanations.
2. **Smart Agent planner** — recognizes supported work instructions and builds a plan.
3. **Tool layer** — performs only approved, allow-listed actions.

This means a normal message such as **"كيف حالك؟"** still receives a normal reply; it is not treated as a tool request.

## Facebook Smart Agent flow

Example:

> غداً الساعة 8 مساء شارك آخر منشور على المجموعات التي يوجد في اسمها كلمة خلدة

The assistant previews:

- source page;
- date/time;
- latest/previous post selection;
- target group keyword;
- current matching group count and examples;
- delay between groups;
- no-repeat window;
- Pending Approval behavior.

It then asks for approval. The user can answer **"نعم"**, **"إلغاء"**, or edit the preview naturally before approval.

Posts accepted by Facebook for group-admin review are recorded as **Pending Approval**, not as failed submissions.

## Interface

The main shell is intentionally similar to modern chat applications:

- **Chat** is the default screen.
- **Settings** lives in the lower-left sidebar rather than occupying the main interface.
- **Activity** contains technical events and errors instead of dumping them into the conversation.
- **Advanced** contains Facebook login/session/group discovery and diagnostics.

## 4 GB RAM behavior

- No model loads at app startup.
- Only one local model is loaded at a time.
- Default: 768 context tokens, 2 CPU threads, 160 reply tokens.
- Local AI runs outside the Tk UI thread.
- If llama.cpp drops the connection, it retries once in low-memory mode.
- Browser automation is lazy and does not launch at app startup.

## Local AI models

- Arabic Agent: `RightNow-Arabic-0.5B-Turbo-q4_k_m.gguf`
- General Agent: `Qwen3-0.6B.Q4_K_M.gguf`

GitHub Actions downloads and verifies the model files and llama.cpp Windows runtime during the build.

## Branding and trust

The original Your Assistant Agent branding remains on the splash, executable icon, taskbar icon, installer and uninstall metadata. The workflow supports optional Authenticode signing when a real code-signing certificate is configured. It does not attempt to bypass antivirus or SmartScreen.

## GitHub Actions

The project ships exactly one workflow:

`.github/workflows/build-windows.yml`

It verifies the Smart Agent dependencies, runs tests, downloads local models and llama.cpp, builds the one-folder PyInstaller application, runs a packaged startup self-test, optionally signs, builds the Inno Setup installer and uploads the Windows Setup artifact.
