# Your Assistant Agent v1.5.0 — Chat Shell + Resilient Local AI

- Restored the chat-first desktop shell with **Chat / Activity / Settings / Advanced** tabs.
- Kept the Arabic/General agent picker while allowing agent changes from Settings.
- Local AI remains lazy-loaded: no model is loaded at application startup.
- Added automatic one-time recovery when the local llama.cpp connection drops.
- Recovery retry uses a lower-memory mode: 512 context, 1 thread, batch 16.
- Added a persistent local AI diagnostic log under the app data folder.
- Technical errors no longer flood the chat; friendly messages stay in chat and details go to Activity/logs.
- Added adjustable low-memory AI settings for 4 GB laptops.
- Kept one model in RAM at a time and made Stop AI non-blocking for the UI.
- Preserved original branding in the app, splash, executable and installer.
- GitHub project ships exactly one workflow: `.github/workflows/build-windows.yml`.
- Workflow retains packaged EXE self-test and optional Authenticode signing support.
