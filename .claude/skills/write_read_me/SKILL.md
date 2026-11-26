---
name: write_read_me
description: Rewrite readme.md as a step-by-step usage guide for the current app, with the architecture infographic. Writes only readme.md.
disable-model-invocation: true
model: haiku
effort: low
---

Written for: new developers and reviewers who clone the repo and have never run it.

1. Read `CLAUDE.md`, `Makefile`, `ops/compose.yaml`, `.env.example`, and `docs/architecture.md`. Use only what the code and config show. Do not describe planned features as working.
2. Write `readme.md` with these sections, in order:
   - What the app does, in two sentences.
   - Prerequisites: Docker, the Jina and Gemini API keys, and `vm.max_map_count=262144` on the host.
   - Setup: `make env`, fill in `.env`, `make up`.
   - Usage: ingest a PDF (`make demo-ingest`), ask a question (`make demo-ask`), check status (`make document-status`), logs, Flower at 127.0.0.1:5555.
   - Evaluation: `make eval-dataset`, then `make eval-run`. Note that both call paid APIs.
   - Development: `make check`, and where tests and code live.
   - Architecture: embed `docs/images/architecture.svg` and summarize the three flows in one line each.
   - Link to `docs/architecture.md`, `docs/plan.md`, and `CHANGELOG.md`.
3. Each step has a numbered command in a code block and the expected result in one sentence.
4. Keep it short. No secrets, real keys, or personal details. Use placeholder names only.
5. Write only `readme.md`. Do not change code, `.env`, or other docs. Report which sections you wrote and anything you could not verify.
