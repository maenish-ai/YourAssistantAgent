# Research references and limits

Checked availability 2026-11-05; these are primary references, not a claim that all implementation requirements were audited against them.

- [Android foreground-service types](https://developer.android.com/develop/background-work/services/fgs/service-types) and [persistent background work](https://developer.android.com/develop/background-work/background-tasks/persistent): use when designing microphone/screen/service lifecycle. The current app must not be described as having unrestricted background microphone access.
- [Groq rate limits](https://console.groq.com/docs/rate-limits): limits depend on model, account and time. A user request can require several model calls; 5–10 user tasks per day is not a guarantee of free availability. No paid subscription or deployment was configured.
- [Playwright locator guidance](https://playwright.dev/python/docs/locators): prefer semantic locators when they are available. This does not prove that a given desktop app is automatable.
- [MCP security best practices](https://modelcontextprotocol.io/specification/2025-06-18/basic/security_best_practices): relevant if an MCP integration is subsequently designed; none is claimed complete here.
- [Arabic Emirati female Piper model](https://huggingface.co/vadimbelsky/arabic-emirati-female-piper): model metadata returned `license: mit` and revision `f89f1aec8e6486871ffdf8d878c5a39eaf918d60`; metadata alone does not establish all dataset, phonemizer, or redistribution rights. Voice quality and real-device cost/latency were not measured.

The current GitHub relay configuration requires real hosting and an enrollment secret. Free tiers are not assumed available or permanent, and no personal relay was deployed or authenticated in this environment.
