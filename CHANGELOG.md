# Changelog

Read at the start of every session. Each date has 4 to 5 short lines. Move old entries to [ARCHIVE.md](ARCHIVE.md).

## 2026-11-25

- Started milestone 1 scaffold: FastAPI API, Celery worker, Flower, Next.js web, Compose stack, `make check`.
- Added structlog JSON logs with request and job IDs, plus `/health` and an `ingestion.heartbeat` task.
- Dependencies added: fastapi, uvicorn, structlog, celery, redis, pydantic-settings, flower, next, react; dev: pytest, httpx, ruff.
- Local storage is a folder (`data/`, mounted into API and worker), not MinIO. Redis client pinned to 6.1.0 (kombu requires it).
- Stack verified: API `/health`, web, Flower, and worker JSON logs with a heartbeat job ID.
- Open: OpenSearch needs `vm.max_map_count=262144` on the host.
- Added Postgres schema (migration 0001) and a dev seed (0002), applied with `python -m app.migrate`. Added psycopg.
- Open: OpenSearch mappings wait for milestone 1 item 4 (indexing). Milestone 1 items 3 to 6 not started.
