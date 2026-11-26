# Archive

Older session history. Claude reads this file only when a task needs earlier context. It is not loaded at session start. Current decisions and open items are in [CHANGELOG.md](CHANGELOG.md).

## 2026-11-26 (moved from CHANGELOG)

- Celery task definitions moved from `src/app/rag/tasks.py` to `src/app/workers/tasks.py`, next to the Celery app. Task names are unchanged, so queued jobs still run. Imports updated.
- `rag/providers/embedder.py` moved to `src/app/rag/embedder.py`; the `providers/` package is removed. Imports updated.
- Job and document status writes (`set_status`, `record_success`, `record_failure`) moved from `rag/indexing.py` to `src/app/db/jobs.py`. `indexing.py` imports them. `make check`: 84 passed.
- OpenSearch chunk index moved from `src/app/search/opensearch.py` to `src/app/rag/vectorstore.py`; the `search/` package is removed. Imports updated.
- Original-file storage moved from the `src/app/storage/` package to `src/app/rag/document_storage.py`, since it is only used by the RAG ingest and upload flow. Imports updated; `make check` run below.
- Domain exceptions (`StorageError`, `OriginalNotStoredError`, `EmbeddingError`, `RerankError`, `IndexingError`) now live in `src/app/exception_handling/exceptions.py`. `LocalStorage` shares one `_path` check for key validation. `make check`: 84 passed.
- PDF text extraction now uses LlamaIndex's `PDFReader` (`llama-index-readers-file==0.8.0`) instead of calling `pypdf` directly. Bytes go through an in-memory fsspec filesystem, so nothing touches disk. `pypdf` is bumped to 6.1.3, which the reader requires. `make check`: 84 passed.
- Route helpers moved out of `routes.py`: answer and chat steps to `src/app/api/answer_pipeline.py`, upload steps to `src/app/api/upload_pipeline.py`. Upload validation (`validate_upload`, `MAX_UPLOAD_BYTES`) moved to `src/app/storage/` (no `utils/` folder in the layout). `get_embedder` moved to `rag/providers/embedder.py`. Routes now only check requests and call pipelines. `make check`: 84 passed.
- Prompt text (`SYSTEM_INSTRUCTION`, `STREAM_INSTRUCTION`, `INSUFFICIENT_EVIDENCE`) and the style rules (`with_style`) moved to `src/app/rag/prompts.py`.
- Ingest queueing moved out of routes: `queue_document` in `workers/ingest.py` checks the stored original, records the job (`db/jobs.py`), and sends it to Celery. Routes only map a missing original to 409. Storage keys come from `original_key` in `storage/`.
- Collection queries (`insert_collection`, `collection_exists`, `collection_workspace`, `ready_document_ids`) moved to `src/app/db/collections.py`; `store_one` became `store_original` in `src/app/storage/`. Routes only wire them up.
- Dependencies moved to their owners: `get_db` to `src/app/db/connection.py`, `get_storage` to `src/app/storage/`. Storage picks its adapter with `Settings.is_cloud` instead of comparing `app_mode` strings. `make check`: 84 passed.
- Production-code review fixes: split long functions (routes, indexing, retrieval, providers, conversations, tasks) into named helpers under 20 lines; retrieval moved to `rag/retrieval.py`; `IndexJob` bundles indexing arguments; request IDs must use letters, digits, `-`, `_`; middleware typed; eval scoring moved to `src/app/evals/scoring.py` with tests. Single-document cases now hit on any accepted page (previously accepted pages could not count alone). `make check` passes (83 API tests). Rebuilt API and worker: baseline unchanged (4 of 5), chat stream and ingest verified.
- Milestone 1 item 5 built: chat screen (`apps/web/app/chat/`) with conversation list, streamed answers, numbered citations, and a source panel that opens the cited page of the stored original.
- `POST /collections/{id}/chat/stream` streams server-sent events (`conversation`, `delta`, `done`, `error`) and saves a turn only if its citations are valid. Conversations and originals: `GET .../conversations`, `GET .../conversations/{id}`, `GET .../documents/{id}/original`.
- Upload page polls `GET /collections/{id}/jobs/{job_id}` and shows queued, processing, ready, or failed per file. Collection Instructions now go into the system prompt for `/ask` and chat, below the citation rules.
- Answer format and length are set per collection (upload form) and added to the system prompt for `/ask` and chat.
- Repo moved from `services/api/` to `src/` (uncommitted). Ingest, search, and ask routes exist with tests, but were not logged until now.
- Local stack: Postgres `rag` user password was out of sync with `.env` (old volume). Fixed with `ALTER USER`; `make up`, `make migrate`, and `make check` pass.
- Milestone 1 item 3 built: collection form and multi-file upload page (`apps/web/app/page.tsx`), then one ingest call per stored file with per-file status. Browser calls the API directly, so CORS is set by `WEB_ORIGINS` (default localhost:3000).
- Web unit tests (`npm test`, node:test + tsx, no network) now run in the web build stage. `make check`: 56 API tests and web tests pass. CORS preflight checked live.
- Browser check (Playwright): two-PDF batch gave 201 collection, 200 upload, two 202 ingests, and both documents `ready` (worker logged 28 chunks). Mixed batch with a fake PDF showed "failed: File content is not a PDF" beside a queued file. Storage failure checked with curl (same calls as the page): one file blocked at its storage path failed with its own error, the other was queued, and ingest of the blocked file returned 409 with no rows. `.playwright-mcp/` is git-ignored. Page now styled (`apps/web/app/globals.css`). Workspace ID is no longer typed: it comes from build arg `NEXT_PUBLIC_WORKSPACE_ID` (set in `.env`). Replace with login in milestone 2. Postgres (5432) and Redis (6379) are published on 127.0.0.1 for GUI tools; local dev only. Added pgAdmin (127.0.0.1:5050) and RedisInsight (127.0.0.1:5540) containers. Their login comes from `PGADMIN_DEFAULT_EMAIL` and `PGADMIN_DEFAULT_PASSWORD` in `.env`, which are required; `make up` fails until they are set. No job-status polling, so progress stops at "queued". Milestone 1 items stay unchecked until milestone acceptance passes.

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
