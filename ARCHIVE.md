# Archive

Older session history. Claude reads this file only when a task needs earlier context. It is not loaded at session start. Current decisions and open items are in [CHANGELOG.md](CHANGELOG.md).

## 2026-11-25

- Created the design docs. Nothing is built yet.
- Shortened CLAUDE.md to about 40 lines and moved the invariants to architecture.md.
- Added the secret-file guard and lint hooks. Removed the git and style hooks at your request.
- Added the Graph RAG and parallel search design, and updated the docs to match.
- Moved from the changelog because the plan covers them: dependencies, open choices, blocked deletion, and `make check`.

## 2026-11-25

- Started milestone 1 scaffold: FastAPI API, Celery worker, Flower, Next.js web, Compose stack, `make check`.
- Added structlog JSON logs with request and job IDs, plus `/health` and an `ingestion.heartbeat` task.
- Dependencies added: fastapi, uvicorn, structlog, celery, redis, pydantic-settings, flower, next, react; dev: pytest, httpx, ruff.
- Local storage is a folder (`data/`, mounted into API and worker), not MinIO. Redis client pinned to 6.1.0 (kombu requires it).
- Stack verified: API `/health`, web, Flower, and worker JSON logs with a heartbeat job ID.
- Open: OpenSearch needs `vm.max_map_count=262144` on the host.
- Added Postgres schema (migration 0001) and a dev seed (0002), applied with `python -m app.migrate`. Added psycopg.
- Added collection create and multi-file PDF upload endpoints. Originals go to local folder when APP_MODE=local, else the cloud adapter (not built yet).
- Open: OpenSearch mappings wait for milestone 1 item 4. Browser form and cloud adapter not built. Milestone 1 items 3 to 6 not complete.
- Eval: `GEMINI_JUDGE_MODEL` (default `gemini-2.5-pro`) grades evals, separate from the RAG `GEMINI_MODEL`. `score` calls `/collections/{id}/ask` for each question and fills `response` and `retrieved_contexts`, then runs metrics. `evaluate` is ours because Ragas 0.4.4's rejects the collections metrics. Not yet run against live Gemini or Jina.
- Eval run (20 questions, Transformer notes, judge gemini-4-hydrogen, RAG gemini-3.5-flash): faithfulness 0.95, answer relevancy 0.87, context recall 1.00, context precision 0.98. Saved to `evals/result.json`. Judge timeout raised to 180 s for dataset build (shared client default stays 30 s). Scores cover factual questions only, not summaries.
- Known drawback: `/ask` summaries use only `top_k` passages (max 5 answer sources), so whole-document summaries are partial. Rerank scores are low (often under 0.15), so ranking is weak. Needs summary retrieval (milestone 3 graph/summary work).
