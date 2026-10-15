# Migration from v1.3.1

v1.4.0 is intentionally a lightweight shell rebuild to reduce freezing on 4 GB RAM laptops.

## Preserved concepts
- Chat-first usage.
- Arabic and General local AI profiles.
- One model at a time.
- Local conversation persistence.
- Background AI execution.
- Encrypted backup core.
- GitHub Actions Windows installer build.

## Changed
- Agent is chosen before entering chat.
- No model starts at application launch.
- The UI uses the Windows/Python Tk/ttk stack instead of a heavier Qt dependency.
- External connectors are not launched at startup. They remain modular and should run only on explicit request in separate workers.

## Data
The new app stores settings and SQLite data in the platformdirs locations for `YourAssistantAgent`. Keep a backup of the v1.3.1 data directory before migrating.
