# Archive

Older session history. Claude reads this file only when a task needs earlier context. It is not loaded at session start. Current decisions and open items are in [CHANGELOG.md](CHANGELOG.md).

## 2026-11-25

- Created the design docs. Nothing is built yet.
- Shortened CLAUDE.md to about 40 lines and moved the invariants to architecture.md.
- Added the secret-file guard and lint hooks. Removed the git and style hooks at your request.
- Added the Graph RAG and parallel search design, and updated the docs to match.
- Moved from the changelog because the plan covers them: dependencies, open choices, blocked deletion, and `make check`.
