# Your Assistant Agent v1.7.0 — Hammer Smart Agent

## Main change
- Removed the visible Arabic Agent / General Agent chooser.
- Added **Hammer 2.1 0.5B Q4_K_M** as the single local Smart Agent model.
- Hammer handles ordinary non-trivial conversation and chooses from an allow-list of tools.
- Instant greetings such as "كيف حالك؟" still reply without loading the model.

## Agent safety and workflow
- No arbitrary Python or CodeAgent execution is exposed.
- External/mutating actions remain behind the existing approval gate.
- Facebook campaign requests are routed by Hammer and converted into a reviewable plan before saving/execution.
- Deterministic Arabic parsing remains as a fallback if a local tool-call template fails.

## Interface
- Chat remains the home screen.
- Sidebar: Chat / Status / Settings / Advanced, with Arabic + English labels by default.
- Added live Status timeline with automatic updates for Facebook connection, post lookup, group-by-group sharing, pending approval, failures, and completion.
- Settings now show the active Hammer model, its license, interface language, Facebook defaults, and low-memory tuning.

## Performance
- One model file only in the installer (~398 MB Q4_K_M).
- Lazy load on first real request.
- 4 GB defaults: context 768, 2 CPU threads, single llama.cpp server.
- One automatic low-memory retry remains enabled by default.

## Model notice
Hammer 2.1 is distributed under CC BY-NC 4.0 by its model repository. This build is intended for personal/non-commercial use. See `THIRD_PARTY_HAMMER.md`.
