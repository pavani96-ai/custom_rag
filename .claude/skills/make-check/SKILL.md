---
name: make-check
description: Run make check in Docker and report only the lint and test failures.
disable-model-invocation: true
model: haiku
effort: low
---

1. Run `make check`.
2. Report pass or fail. On failure, list only the failing files, tests, and error lines.
