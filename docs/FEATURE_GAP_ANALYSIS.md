# Feature gap analysis

Labels: **tested** means covered by the local tests identified in the architecture audit, not a production or device certification. **partial** means code exists but the requested feature is incomplete or not fully verified. **device test** means no physical-device/end-to-end evidence in this environment.

| Area | Status | Evidence and remaining gap |
|---|---|---|
| Python startup, agent and file primitives | Tested / partial | Existing Python suite and focused tests pass on Linux with mocks and local fixtures. Windows UI automation and packaged startup require Windows. |
| Relay encryption, request IDs, replay/expiry | Tested / partial / device test | `tests/test_relay.py`, AES-GCM protocol and replay DB exist. No deployed personal relay or real cross-network end-to-end test. Broker queues are in memory. |
| Android pairing, crypto, lifecycle and file client | Tested / partial / device test | 33 Robolectric/JVM tests and local debug build passed; no physical Samsung, network switching or background endurance test. |
| Remote desktop image/control | Partial / device test | Existing screen and input endpoints; no measured adaptive WebRTC stream or 4 GB performance result. |
| Voice Arabic | Partial / device test | Groq STT and Android TTS/call loop exist. No verified quality by dialect, full duplex, reliable interruption, or live physical microphone test. Voice model and licensing need verification. |
| Task planner, desktop execution | Partial | Bounded loop and approval; limited verification, no durable general-purpose plan/checkpoint engine, no trustworthy vision fallback and no complete document analysis workflow. |
| Memory | Partial | SQLite explicit notes and error codes; no automatic procedural/semantic RAG, conflict management or guaranteed encryption of notes. Notes are sent to the configured model as context. |
| Scheduler/social | Partial / device test | Facebook-specific rules and approval exist; no general durable scheduler for all tools, no verified WhatsApp broadcasts or real platform account tests. |
| Integrations/plugins | Partial | Internal tools and some connectors; no full capability-scoped plugin lifecycle or generalized MCP integration. |
| Builds | Partial | Both jobs exist in one workflow; Android local debug build tested. No fresh Windows installer or confirmed GitHub Actions run. Android release requires matching private signing key. |
| Permission modes, offline queue, per-device revoke | Not established | No evidence for the complete requested modes, safe offline queue or independently revocable paired-device inventory; do not claim them. |
| Performance | Not tested | No real idle, streaming or CPU/RAM measurements on the target 4 GB Windows machine. |

## Acceptance scenarios

01 QR pairing: unit/simulated tests only; physical **not tested**. 02 Internet: **not tested**. 03 reconnect: protocol tests only; physical **not tested**. 04 Windows: **not tested**. 05 browser: simulated extension tests; real site workflow **not tested**. 06 files: temporary-files tests, not phone-to-Windows **not tested end-to-end**. 07 Arabic voice: **not tested** on devices. 08 recovery: focused unit tests only. 09 screen sharing: tests cover components; physical start/stop **not tested**. 10 permissions: unit tests, no independent audit. 11 low-memory: **not tested**. 12 social: **not tested** on actual account. 13 GitHub: local Git fixture tests; actual remote push **not tested**. 14 background tasks/restart: general workflow **not tested**. 15 security: targeted unit tests; independent penetration test **not performed**.

## Stage A changes in this branch

- Separate Windows/Android workflow definitions and tests for the split; GitHub-hosted workflow runs remain **not tested** on this branch.
- Browser bridge rejects regular web origins and oversized requests; this is **partial**, since extension identity is not authenticated and no real-browser compatibility test has been completed.
- Model download uses a pinned revision and content hashes. Upstream metadata reports MIT, but all underlying redistribution terms are **not verified**.
- Phone file provenance and failure reporting have focused tests; they remain **not tested end-to-end** on Windows/Android.
