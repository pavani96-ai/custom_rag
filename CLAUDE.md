# Project instructions

Private document workspace: ingests documents, answers with verified citations, and runs exact calculations over structured data. Stack: Next.js, FastAPI, Celery, LlamaIndex, PostgreSQL, OpenSearch, Redis, Cloud Storage, Vertex AI, Document AI, Docker Compose locally, GKE and Terraform in the cloud.

## Read first

- [docs/architecture.md](docs/architecture.md): boundaries, API contracts, cache identities, and the invariants. Read it before changing routes, retrieval, citations, or ingestion.
- [docs/plan.md](docs/plan.md): milestone order and acceptance checks.
- [CHANGELOG.md](CHANGELOG.md): decisions, dependencies, and open items. Read at session start.
- [ARCHIVE.md](ARCHIVE.md): older history. Read only when a task needs earlier context.

At the end of each session, add a dated entry to CHANGELOG.md. Move entries that no longer affect future work to ARCHIVE.md.

## Workflow

- Pass a milestone's acceptance checks before reporting it done; keep its checkboxes unchecked until then.
- Extend earlier interfaces rather than replacing them.
- When a design decision changes, update the relevant doc in the same change.
- Report verification gaps and blockers first.

## Layout

- `apps/web/`: Next.js UI
- `src/app/api/`: FastAPI app (`main.py`) and all HTTP routes (`routes.py`)
- `src/app/rag/`: extraction, chunking, indexing, Celery tasks; `rag/providers/` holds Jina embedding and reranking clients
- `src/app/search/`: OpenSearch index mapping and bulk indexing (`opensearch.py`)
- `src/app/config/`: settings from environment and `.env`; `src/app/workers/`: Celery app
- `src/app/schema/models.py`: every Pydantic request, response, and provider payload model
- `src/app/db/`: migration runner and SQL migrations (`db/migrations/`); `src/app/storage/`: original-file storage; `src/app/observability/`: JSON logs
- `src/tests/`, `ops/api.Dockerfile`: API image (build context is `src/`)
- `evals/`, `ops/`, `infra/terraform/`

## Commands

- `make env`: create `.env` from `.env.example` (then fill in the placeholders)
- `make up` / `make down` / `make logs`: local stack via Compose (API on 127.0.0.1:8000, Flower on 127.0.0.1:5555)
- `make check`: lint and tests for the API, and typecheck and build for the web, all in Docker

## Conventions

- SQL is backend-generated, parameterized, and read-only.
- Printed scans: Docling with RapidOCR. Marked handwriting: Document AI.
- Keep operational IDs and upload time out of model and embedding text.
- Count provider calls in tests to verify cache reuse.

## Do not

- Commit `.env` files, credentials, or Secret Manager values.
- Add provider calls that bypass leases and cache identities.
- Expand scope beyond the requested milestone without asking.
