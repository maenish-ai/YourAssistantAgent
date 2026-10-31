# YourAssistantAgent v4.3.0 — Reviewed ZIP-to-GitHub upload

- Added explicit ZIP → GitHub button to the v4.2 chat attachment toolbar.
- Recognizes natural upload requests mentioning GitHub and opens the same review/approval UI.
- Validates ZIP entries before extracting, blocks traversal, symlinks, duplicate paths, secret-looking files and archive size abuse.
- Verifies selected local checkout origin is `maenish-ai/YourAssistantAgent` and working tree is clean.
- Shows added/modified/unchanged file counts and destination branch before any write.
- Requires affirmative UI approval before copying ZIP entries into the repository and running `git add`, `git commit`, and `git push`.
- Uses existing local Git/GitHub Desktop authentication; never sends Git credentials or ZIP bytes to GroqCloud.
- Reports push failures without claiming success; local commit can remain for manual review in GitHub Desktop.
- Bumped installer, Windows executable and package metadata to 4.3.0.
- Added 17 isolated safety and publishing tests (mocked push, no actual GitHub mutation).

Known limitations: only one archive per upload, only the configured YourAssistantAgent repository, clean local working tree required, no line-by-line diff UI, Git authentication must already work, and Windows UI/installer must be tested on Windows.
