# Document workspace implementation plan

Build a private workspace that ingests documents, answers with verifiable citations, and performs exact calculations over structured data. Start with a working local flow and promote the same containers through Google Cloud staging and production. The [architecture](architecture.md) defines the API contracts, cache identities, and activation rules.

## Proposed repository layout

| Path | Responsibility |
|---|---|
| `apps/web/` | Next.js workspace, upload and chat UI, citations, charts |
| `src/app/api/` | HTTP app: `main.py` (FastAPI entry point) and `routes.py` (all routes: collections, uploads, search, answers) |
| `src/app/schema/` | Pydantic request, response, and provider payload models (`models.py`) |
| `src/app/config/` | Settings loaded from environment variables and `.env` (`settings.py`) |
| `src/app/workers/` | Celery worker app (`celery_app.py`) |
| `src/app/db/` | PostgreSQL migration runner (`migrate.py`) |
| `src/app/storage/` | Original-file storage adapters (local folder now, cloud later) |
| `src/app/rag/` | Extraction and chunking (`pipeline.py`), indexing, and Celery tasks (`tasks.py`) |
| `src/app/search/` | OpenSearch index mapping and bulk indexing (`opensearch.py`) |
| `src/app/rag/providers/` | Jina embeddings and reranking clients |
| `src/app/observability/` | Structured JSON logging |
| `src/app/db/migrations/` | PostgreSQL schema and migrations (run by `db/migrate.py`) |
| `src/tests/` | Unit and integration fixtures, including synthetic PDFs and spreadsheets |
| `evals/` | Versioned datasets, metric runners, reports, and regression thresholds |
| `ops/` | Docker Compose, Kubernetes manifests, collector settings, and dashboard definitions |
| `infra/terraform/` | Cloud resources, with separate staging and production environments |

## 1. Prove the local document workflow

- [x] Scaffold Next.js and FastAPI, package the API and worker as Docker images, and run both with PostgreSQL, OpenSearch, Redis, and local object storage through Compose. Add structlog JSON logging to the API and worker, and run Flower privately in Compose.
- [x] Add migrations for workspaces, collections, documents, jobs, outbox records, artifact metadata, active index pointers, and chat history. Create OpenSearch mappings for chunk text, vectors, and retrieval metadata. Provide a seeded local identity for the development fixture and establish the workspace scope in service interfaces.
- [x] Build the collection setup flow with title, description, instructions, and response preferences. Add multi-file upload with per-file status. Store each original durably, then have the browser automatically call the ingest endpoint with the finalized upload IDs. Show a per-file error if storage fails and queue indexing only for files whose originals are stored.
- [x] Implement `POST /collections/{collection_id}/documents/ingest` and its worker. Record each document with its pinned original, queue first-time indexing, and return HTTP 202 with per-document job IDs for progress tracking. Track document status as `queued`, `processing`, `ready`, or `failed`; only `ready` documents are searchable. Parse two digital PDFs, persist page locations, build stable LlamaIndex node IDs and links, embed chunks, store vectors in OpenSearch, and activate the index.
- [x] Stream a cited answer through the browser using exact scoped retrieval. Persist the turn and build a source viewer that resolves each citation.
- [x] Freeze a small versioned set of independently written questions, reference answers, and expected document and page IDs. Include exact identifiers, a question spanning both PDFs, and an unanswerable question. Record the exact-search baseline before tuning retrieval.
- [x] **Acceptance** — Upload two PDFs and verify that indexing starts automatically. Ask a question that requires both and open both cited pages from the stored originals. Force a storage failure for one file and verify that it has a visible error and no indexing job. Restart the app and worker and reopen chat history and citations. Ask an unanswerable question and verify explicit abstention. Verify that API and worker logs are JSON with request and job IDs, and that Flower shows the ingest task.

## 2. Make ingestion repeatable and private

- [ ] Add production authentication, workspace membership checks, and consistent authorization for uploads, jobs, chat, datasets, and citations.
- [ ] Implement resumable Cloud Storage uploads, quota reservations, and pinned object generations. Allow a browser to skip a duplicate upload only when the caller can read an existing source containing those bytes and can add documents to the destination collection. Otherwise use the normal upload and verification flow. Add deletion with reference-aware cleanup.
- [ ] Scope recent-turn Redis memory to the authorized conversation, expire it with a TTL, and rebuild it from committed PostgreSQL messages on a miss. Recheck access before returning history or using cached turns.
- [ ] Add `POST /collections/{collection_id}/documents/{document_id}/reingest` and a UI action for reprocessing a stored document, for example after a transcript correction or a chunking change. Read the pinned original by document ID. Persist extraction, enrichment, and embedding cache keys so the worker can reuse valid results. Instrument external dependency calls so tests can count them.
- [ ] Implement staged runs, durable outbox dispatch, bounded retries, and fenced activation. Claim each missing artifact with a renewable database lease before calling a provider. Reconcile expired claims and check for committed results before retrying. Reuse provider idempotency keys where supported and record attempts for the crash window between provider success and local commit.
- [ ] Add a collection settings action to migrate embedding profiles. Stage vectors of the target dimensions separately, reconcile uploads, edits, and deletions during the build, then atomically activate the matching query profile and index.
- [ ] **Acceptance** — Repeat the same upload through the browser as an authorized reader and verify zero file bytes transferred. A user with access only to a different collection in the same workspace gets the ordinary upload flow and cannot infer a hash match, link the protected source, or read its contents. Repeat with a second workspace. Reingest an already indexed document and verify zero new embedding calls.
- [ ] **Recovery checks** — Deliver overlapping jobs for the same missing artifact and verify one calculation while the lease is valid. Kill a worker before its provider call and after provider success but before commit. Verify lease recovery, bounded retries, a single published artifact, and observable potentially repeated charges when provider idempotency is unavailable.
- [ ] **Migration and memory checks** — Migrate to different embedding dimensions while uploading, reingesting, and deleting documents. Verify consistent search before and after cutover, preserved IDs for unchanged chunks, and immediate loss of access to deleted sources. Expire a conversation cache, verify follow-up context reloads from PostgreSQL, and test isolation between conversations and users.

## 3. Add production retrieval and document formats

- [ ] Add an OpenSearch BM25 keyword branch alongside the OpenSearch vector branch with shared access filters. Add reciprocal rank fusion and reranking. Record candidate IDs before and after reranking.
- [ ] Add DOCX, TXT, and Markdown extraction. Add Docling with RapidOCR for printed scans and mixed PDFs, with a bounded full-page retry. Preserve page and table provenance from structured output.
- [ ] Add a handwriting option and page selection. Route marked pages to Document AI, preserve confidence and bounding boxes where available, and support corrected transcripts through reingestion.
- [ ] Compare the baseline with question-enriched chunks on the frozen milestone 1 cases, using identical retrieval settings. Add independently labeled scan cases before tuning OCR. Adopt one enrichment only if the held-out benchmark shows a gain worth its cost. Consider parent expansion when missed answers require more section context.
- [ ] Add Graph RAG on by default. Extract entities and relationships at ingest into a graph store, and build document and collection summaries from them. Run keyword, vector, and graph retrieval in parallel for every question, merge with reciprocal rank fusion, and rerank. Do not add a query classifier. Cache extraction and summary calls by enrichment identity, and remove graph entities and summaries when a document is deleted. Compare this fan-out against the hybrid-only baseline on the frozen cases, recording latency and cost per query.
- [ ] Add a bounded vision path for retrieved charts or ambiguous handwriting. Trial ColPali only if visual pages frequently miss candidate retrieval.
- [ ] **Acceptance** — Answer a question requiring a digital and scanned PDF. Test a mixed PDF, a broken text layer, and handwritten entries on a printed form. Verify citations, names and numbers, and abstention for unreadable details. Report dense, hybrid, and reranked evidence recall separately. Ask a summary question across both documents and verify the graph branch contributes evidence to the answer. Ask a specific fact question and verify that candidate IDs from each branch are recorded before and after reranking.
- [ ] **Cache check** — Ingest a new scanned fixture using a profile with question enrichment enabled. Assert that the first run invokes OCR, enrichment, and embedding. Restart the API and workers, reingest with the identical profile, and assert zero additional calls to each stage with the expected citations still retrievable.

## 4. Compute exact spreadsheet answers

- [ ] Parse CSV and XLSX into versioned typed tables with dataset schema, units, source rows, and import warnings. Add dataset descriptions to scoped retrieval.
- [ ] Pin the analysis request, SQL execution, chart, and citations to one authorized dataset version. Validate aggregates, filters, groups, and period comparisons and translate them to bounded read-only SQL. Preserve duplicates unless the request defines a deduplication rule. Count missing numeric cells separately and preserve zeroes. Ask for clarification before aggregating mixed currencies. Flag missing or known-stale formula values and request a recalculated value before computing an affected result.
- [ ] Return computed results with provenance and filters. Render charts from the computed data. Add a combined path that uses computed results to find explanatory passages.
- [ ] **Acceptance** — Calculate monthly spend by department and identify the largest month-over-month increase. Verify exact amounts, the displayed chart, and citation provenance. Cover missing values, duplicates, ambiguous periods, mixed currencies, and cross-workspace access. Ask a mixed question and verify independent citations for the calculation and explanation.
- [ ] Reingest a changed workbook while an analysis is running and verify its result, chart, and source rows all refer to the pinned version. Test an all-blank group, a group containing an explicit zero, duplicate rows, and formulas with missing or known-stale values. Verify missing-value counts and that the system withholds the affected result when a required formula is unusable.

## 5. Measure quality and diagnose failures

- [ ] Expand the versioned milestone 1 and 3 fixtures with handwriting, visual evidence, and multi-format questions. Preserve earlier baselines, record reference answers and expected source IDs, and report results by document type.
- [ ] Add a small Ragas CI run and a scheduled full run. Pin models and experiment settings, establish a human-reviewed baseline, and publish results per document slice. Keep deterministic citation and numeric tests in the regular suite.
- [ ] Add Prometheus scraping and Grafana dashboards for API and workers, covering request, error, latency, queue age, retry, and cache-hit metrics. Keep Flower private. Add OpenTelemetry tracing with trace IDs attached to structlog output. Add LangSmith or Langfuse for redacted LLM and retrieval traces.
- [ ] **Acceptance** — Force an ingestion failure and follow it from the UI job state to worker and API telemetry. Verify that Grafana displays application and span-derived metrics, including cache hits. Inspect hosted traces for private data and demonstrate how evaluation identifies extraction, retrieval, and answer failures.

## 6. Deploy and verify on Google Cloud

- [ ] Use Terraform to provision VPC, GKE, Cloud SQL for PostgreSQL, separate Redis broker and cache capacity, private buckets, Artifact Registry, Secret Manager, workload identities, and alert policies. Keep state remote and environments separate.
- [ ] Add deployment manifests for UI, API, Celery workers, outbox publisher and reconciler, collector, and Flower. Set `APP_MODE=cloud` on GKE and configure OpenTelemetry export to Cloud Monitoring, Cloud Logging, and Cloud Trace. Define Cloud Monitoring alerts for queue age, worker loss, API errors, and saturation. Configure resource limits, readiness, graceful job shutdown, and private operational access.
- [ ] Deploy private OpenSearch on GKE with persistent disks and snapshot backups. Verify that restoring an index preserves retrieval and citations.
- [ ] Configure a Google Cloud Application Load Balancer to route HTTPS traffic to healthy Next.js and FastAPI replicas on GKE. Configure horizontal scaling for the web and API deployments and scale Celery workers independently with ingestion demand.
- [ ] Configure CI/CD to build immutable images, run tests and evaluation, review Terraform plans, run migrations, and deploy staging before production. Document compatibility requirements for schema changes and rollback.
- [ ] **Acceptance** — In staging, exercise upload, reingestion, handwriting, cited chat, spreadsheet analysis, and telemetry from the browser. Verify that a test request produces metrics in Cloud Monitoring, correlated logs in Cloud Logging, and spans in Cloud Trace. Verify a backup restore, rehearse rollback, and load-test chat and ingestion together. Verify that the load balancer serves traffic across healthy replicas and that chat follow-ups still resolve when routed to a different API replica. Promote the verified build to production and run a synthetic smoke test.

## 7. Expand supported sources

- [ ] Add PPTX and expand table or layout extraction based on evaluation. Add URL ingestion with public URL restrictions, redirect and destination validation, limits, and source tracking.
- [ ] Add Google Drive, OneDrive, and SharePoint connectors. Specify whether each flow imports a snapshot or synchronizes changes. Test token expiry, source deletion, and authorization revocation for synchronized files.
- [ ] **Acceptance** — Import each supported source, show provenance, and confirm edits or access changes propagate according to the selected connector behavior.
