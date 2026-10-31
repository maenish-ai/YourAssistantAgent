# Your Assistant Agent v2.9.0 — Cloud-first idle safety

## Why this release exists
Several users' Windows laptops became unresponsive while the agent was idle. The root cause of every specific freeze has **not** been proved. This patch removes the known unnecessary recurring background work and stops automatic legacy activity by default. It is a conservative stabilization pass, **not** a full rewrite or a guarantee that hardware will not freeze.

## Behavior changes (intentional, one-time migration)
* `X` = exit the application, rather than silently stay in the tray.
* Remove **this application's own** HKCU `Run` value on Windows (`start_with_windows=off`). No unrelated startup items are touched.
* Facebook session auto-check OFF; user can check it on demand.
* Automatic backup/sync OFF; existing backup data remain intact and manual backup remains available. User can re-enable in settings.
* Unattended scheduled tasks OFF by default; existing rules remain saved. Re-enable with the **Background tasks (opt-in)** checkbox on the Tasks page, with explicit confirmation. "Run now" still works on user request.
* New user defaults are safe; existing pre-v2.9 settings migrate once. Explicit v2.9 preferences are preserved on subsequent loads.
* Installer's "Launch" checkbox is unchecked by default after installation.

## Local activity reduced
* Chat queue check: ~100 ms **during** an active response or voice, 1.6 s idle (5 s when hidden).
* Sidebar status check: 20 s idle (60 s hidden), 4 s if a task is running.
* Cloud AI model unloading timer removed: no local model to unload.
* Background backup timer installed only if backups were opted in; duplicate idle-based re-arming removed.
* Facebook rule scheduler does not start without explicit permission and at least one enabled rule. If opted in, it checks on a 30 s cadence instead of every 2 s.
* Browser bridge remains available for requested browser actions; no automatic Facebook login check on startup.

## Intact functionality
* GroqCloud GPT-OSS text and tool interaction; Whisper and Noura/Sana options; existing v2.8 mic diagnostic; approval UI; GitHub Desktop button; saved user chats, account sessions, tasks, and data.
* No new runtime dependencies and no local models added.

## Risks and test coverage
* Intended for a **full v2.8 project** — extracted ZIP alone is not an executable project.
* The Windows GUI and hardware/audio path cannot be tested here; final Actions build and a cautious short local test are required.
* Some older layers still exist for backwards compatibility. A true single-layer rewrite remains separate engineering work.
* Opted-in backup/scheduled tasks inherently consume disk/CPU while they run.
