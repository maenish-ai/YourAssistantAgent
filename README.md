# Your Assistant Agent v1.4.1 — Lite Agent Picker

A clean Windows-first rebuild focused on 4 GB RAM laptops and avoiding UI freezes.

## What changed in v1.4.1

- **Agent picker before chat**: Arabic Agent or General Agent.
- **Only one local model can be loaded at a time.**
- **Lazy AI loading**: opening the app and entering chat does not load a model. The selected model starts only when a real AI request needs it.
- **GUI never waits for AI**: model startup and inference run on a background worker thread.
- **Enter sends / Shift+Enter inserts a new line.**
- **Fast path for tiny greetings** so messages such as `كيف حالك؟` do not boot a 400+ MB model unnecessarily.
- **4 GB defaults**: 1024-token context, 2 CPU threads, 220 max response tokens, single parallel slot.
- **Stop AI** button releases the model process from memory.
- SQLite uses WAL mode so chat writes do not block the interface.
- Source repository stays small. GitHub Actions downloads and verifies both GGUF files during the Windows build.

## Local AI profiles

### Arabic Agent
`RightNowAI/RightNow-Arabic-0.5B-Turbo` — Q4_K_M, about 424 MB.

### General Agent
`Qwen3-0.6B` — Q4_K_M quantization used by this build, about 484 MB.

The installer contains both model files, but the app never loads both into RAM simultaneously.

## Run from source

Python 3.11+ is recommended.

```powershell
py -3.11 -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -r requirements.txt
$env:PYTHONPATH = "$PWD\src"
python -m yaa_lite.main
```

For local AI from source, place `llama-server.exe` and its required DLLs under `runtime/`, and place the model files under `models/` using the names in `models.manifest.json`.

## Tests

```powershell
pip install -r requirements-dev.txt
$env:PYTHONPATH = "$PWD\src"
pytest -q
```

## GitHub build

Push the repository to `main`, then open **Actions → Build Windows Setup**. The workflow:

1. installs dependencies;
2. downloads both GGUF models;
3. verifies their SHA-256 hashes;
4. downloads the latest Windows x64 CPU llama.cpp runtime;
5. runs tests;
6. builds a PyInstaller folder;
7. creates one Inno Setup installer artifact.

## Backup

`src/yaa_lite/backup/crypto_backup.py` provides AES-256-GCM encrypted `.yaa` snapshots. The intended cross-device flow is to choose a Google Drive for desktop folder in Settings and save encrypted backups there. The recovery key must be stored separately.

## Important connector note

The lightweight shell deliberately does **not** launch Facebook/browser discovery at startup. Connector work should be invoked only when the user explicitly requests it and should run in a separate worker/process, so a slow browser or network request cannot freeze the chat UI.
