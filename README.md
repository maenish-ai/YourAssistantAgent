# Your Assistant Agent v1.7.0

A lightweight Windows desktop assistant with a ChatGPT-like chat screen and a local Smart Agent.

## What is new in v1.7

The application now exposes **one assistant only**. The old visible Arabic Agent / General Agent selector is gone.

The local model is **Hammer 2.1 0.5B Q4_K_M**. Hammer is used as the action/tool-routing model and can also respond to normal conversation. Very common greetings use an instant fast path, so saying `كيف حالك؟` or `Hello` does not need to load the model.

The main sidebar is intentionally simple:
- **المحادثة / Chat**
- **الحالة / Status** — live automatic progress timeline
- **الإعدادات / Settings**
- **متقدم / Advanced**

## Smart Agent behavior

A normal conversation gets a normal reply. A work request such as:

> غداً الساعة 8 مساء خذ آخر منشور من صفحتي وانشره على الجروبات التي تحتوي كلمة خلدة

is routed through Hammer's allow-listed tools, converted to a plan, matched against saved groups, and shown for confirmation. The app never exposes arbitrary local Python execution to the model.

Facebook execution writes live events to Status, including opening Facebook, locating the source post, each group being processed, pending-admin-approval outcomes, failures, and the final summary.

## 4 GB RAM design
- one GGUF model only (~398 MB)
- lazy model loading
- llama.cpp CPU runtime
- context 768 by default (max 1024)
- 2 CPU threads by default
- one low-memory retry if the local server drops

## Hammer model and license
- Original: `MadeAgents/Hammer2.1-0.5b`
- GGUF used: `Melvin56/Hammer2.1-0.5b-GGUF` / `hammer2.1-0.5b-Q4_K_M.gguf`
- SHA256: `190676fe7ac430ac6680b32c216d4eb7413002e2af0c140b8280a0f74fcc6a4d`
- Declared license: **CC BY-NC 4.0**

This project build is intended for personal/non-commercial use. See `THIRD_PARTY_HAMMER.md` before any commercial distribution.

## Build
Push the project to `main`. The single workflow `.github/workflows/build-windows.yml` downloads and verifies the Hammer GGUF and llama.cpp, runs tests, builds the PyInstaller one-folder app, creates the Inno Setup installer, and uploads the Windows Setup artifact.

Optional Authenticode signing remains supported through the existing GitHub secrets described in `SIGNING_AND_TRUST_AR.md`.
