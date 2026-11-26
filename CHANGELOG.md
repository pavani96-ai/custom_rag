# Changelog

Read at the start of every session. Each date has 4 to 5 short lines. Move old entries to [ARCHIVE.md](ARCHIVE.md).

## 2026-11-26

- Repo moved from `services/api/` to `src/` (uncommitted). Ingest, search, and ask routes exist with tests, but were not logged until now.
- Local stack: Postgres `rag` user password was out of sync with `.env` (old volume). Fixed with `ALTER USER`; `make up`, `make migrate`, and `make check` pass.
- Milestone 1 item 3 built: collection form and multi-file upload page (`apps/web/app/page.tsx`), then one ingest call per stored file with per-file status. Browser calls the API directly, so CORS is set by `WEB_ORIGINS` (default localhost:3000).
- Web unit tests (`npm test`, node:test + tsx, no network) now run in the web build stage. `make check`: 56 API tests and web tests pass. CORS preflight checked live.
- Browser check (Playwright): two-PDF batch gave 201 collection, 200 upload, two 202 ingests, and both documents `ready` (worker logged 28 chunks). Mixed batch with a fake PDF showed "failed: File content is not a PDF" beside a queued file. Storage failure checked with curl (same calls as the page): one file blocked at its storage path failed with its own error, the other was queued, and ingest of the blocked file returned 409 with no rows. `.playwright-mcp/` is git-ignored. Page now styled (`apps/web/app/globals.css`). Workspace ID is no longer typed: it comes from build arg `NEXT_PUBLIC_WORKSPACE_ID` (set in `.env`). Replace with login in milestone 2. Postgres (5432) and Redis (6379) are published on 127.0.0.1 for GUI tools; local dev only. Added pgAdmin (127.0.0.1:5050) and RedisInsight (127.0.0.1:5540) containers. Their login comes from `PGADMIN_DEFAULT_EMAIL` and `PGADMIN_DEFAULT_PASSWORD` in `.env`, which are required; `make up` fails until they are set. No job-status polling, so progress stops at "queued". Milestone 1 items stay unchecked until milestone acceptance passes.

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
