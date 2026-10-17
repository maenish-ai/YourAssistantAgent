# Your Assistant Agent v2.2.0 — Direct Qwen Personal Assistant

A lightweight Windows desktop personal assistant with **one local AI brain: Qwen3 1.7B Q4_K_M**.

The app is no longer designed as “router first, chat second”. In v2.2, ordinary conversation is ordinary Qwen chat. When the user asks for something the app can actually do, Qwen uses its native function/tool-calling format through llama.cpp and the desktop app executes only allow-listed tools.

## Core architecture

`User text/voice -> Qwen3 -> (normal answer OR application tool) -> tool result -> Qwen3 -> user`

There is no `respond` function in the main personal-assistant tool list. If no tool is needed, Qwen answers normally.

The desktop application remains the permission and safety boundary. Qwen never receives arbitrary Python or shell execution.

## Facebook personal-assistant flow

Qwen can now chain safe Facebook operations in one request, for example:

- open the Facebook login page if the account needs manual sign-in;
- verify the Facebook connection;
- refresh joined groups;
- select groups by include keywords;
- exclude groups by keyword or exact name;
- remember the latest group selection inside the current chat when chat memory is enabled;
- draft a campaign and show a deterministic preview;
- after explicit approval, save/run the campaign.

Example natural instruction:

> حدّث الجروبات، اختار كل جروب فيه كلمة الفحص، واستثني الجروب اسمه الفحص التجارية.

The application turns that into a structured group filter rather than relying on brittle string parsing.

Publishing/immediate campaign execution still requires explicit approval. Facebook passwords, 2FA, CAPTCHA and checkpoints remain manual and are never bypassed.

## Native Qwen tool calling

The bundled llama.cpp server starts with `--jinja`, allowing the Qwen chat template to expose OpenAI-compatible tool calls. Qwen may either:

1. return normal assistant text; or
2. request one allow-listed application function.

Safe tools can be executed and fed back to Qwen for another step, with a hard five-step cap per user turn to prevent accidental loops.

## Voice

Push-to-talk remains fully local:

`Microphone -> whisper.cpp -> Qwen3 -> optional app tools -> Piper -> speakers`

The build bundles whisper.cpp, a multilingual Whisper base model, Piper, and the Jordanian Arabic `ar_JO-kareem-medium` voice. Windows SAPI remains a fallback for speech output.

## Local AI model

- Base model: `Qwen/Qwen3-1.7B`
- GGUF: `ggml-org/Qwen3-1.7B-GGUF`
- File: `Qwen3-1.7B-Q4_K_M.gguf`
- SHA256: `d2387ca2dbfee2ffabce7120d3770dadca0b293052bc2f0e138fdc940d9bc7b5`
- License: Apache-2.0

Legacy source/database names containing `hammer` remain only as compatibility aliases so existing chats and tasks continue to open. The shipped model is Qwen, not Hammer.

## Build

Push the overlay to `main`. The single `.github/workflows/build-windows.yml` workflow downloads and verifies Qwen, llama.cpp, whisper.cpp and Piper, runs tests, builds the PyInstaller app, smoke-tests it, creates the Inno Setup installer and uploads the installer artifact plus SHA256.
