# Your Assistant Agent v1.0.0

- Added hybrid AI Brain + safe local parser for employee-like natural-language campaign understanding.
- Added OpenAI Responses API structured interpretation with configurable model and DPAPI-protected API key.
- Added conversational clarification context for desktop Smart Agent and Telegram Remote.
- Added fail-closed behavior when audience/filter intent is ambiguous.
- Improved dynamic Arabic group-name extraction; arbitrary names are treated as entities rather than hard-coded locations.
- Added semantic Facebook share outcomes: `published`, `submitted`, `pending_approval`.
- Admin/moderator approval is no longer treated as a failed share.
- `submitted` and `pending_approval` are included in duplicate prevention, so the same post is not re-sent while awaiting approval.
- Added Arabic dashboard labels and audit events for published/submitted/pending-approval outcomes.
- Bumped package/installer to 1.0.0.
- Existing GitHub Deployment, Telegram Remote, Wake/Sleep, group discovery, and Setup-only workflow remain intact.
- Full merged test suite: 30 passed.
