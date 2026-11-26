# Document workspace architecture

## Product scope

A workspace contains private document collections. The UI may call a saved collection configuration a custom agent. It stores a name, description, instructions, sources, and preferences for tone, structure, and presentation. The application runs fixed workflows for document answers, structured calculations, and questions that need both. The Next.js workspace has its own design with setup, sources, settings, and chat views.

## Components

| Component | Responsibility |
|---|---|
| Next.js | Collection setup, direct upload, file and job status, chat streaming, source viewer, and charts |
| FastAPI | Authentication, authorization, upload and job APIs, retrieval, analysis, and streaming |
| Celery | Extraction, OCR, enrichment, embedding, reingestion, and cleanup |
| LlamaIndex | Orchestration framework: linked nodes, retrieval, reranking calls, context assembly, and answer generation (Gemini via `GoogleGenAI`). Provider clients such as Jina and OpenSearch stay native so their settings can be changed directly. |
| PostgreSQL | Workspaces, memberships, collections, document and artifact metadata, job and outbox state, chat history, structured datasets, and active index pointers |
| OpenSearch | Searchable chunks, embeddings, keyword indexes, and retrieval metadata |
| Redis | Recent conversation turns with a TTL, other short-lived caches, and rate limits, with a separate Celery broker in production |
| Cloud Storage | Private, durable raw files and versioned extraction artifacts |
| Vertex AI | Initial generation and embedding provider behind separate application interfaces |
| Google Document AI | Handwriting OCR and an approved fallback for difficult printed scans |
| GKE | Runs versioned Docker images for the application, workers, and operational services |
| Graph store | Entities and relationships linked to chunks, scoped to the workspace. Queried on every question, alongside keyword and vector search. Technology is chosen at the milestone 3 gate. |
| structlog | Structured JSON logs from FastAPI and Celery, with request, job, and conversation IDs |
| Flower | Private Celery dashboard for workers, queues, tasks, and retries |
| Prometheus and Grafana | Metrics and dashboards. Local first, then on GKE |

Use Docker Compose locally, with a local object-storage adapter for automated tests and optional access to a development bucket for integration tests. Production uses Cloud SQL, Memorystore, Cloud Storage, Secret Manager, Artifact Registry, and GKE with workload identity. Run OpenSearch as a private stateful workload on GKE with persistent disks and snapshot backups. Terraform owns cloud infrastructure. Kubernetes manifests own application deployment and health checks.

A Google Cloud Application Load Balancer routes HTTPS traffic to healthy Next.js and FastAPI replicas on GKE. Scale the web and API deployments horizontally and independently. API replicas share conversation state through PostgreSQL and Redis so follow-up requests can reach any healthy replica. Celery workers consume from Redis and scale independently with ingestion demand. Browser uploads continue directly to Cloud Storage.

## Code layout

The API lives in `src/app/`. Each folder owns one concern:

| Folder | Owns |
|---|---|
| `api/` | FastAPI entry point (`main.py`) and all HTTP routes (`routes.py`) |
| `rag/` | Extraction, chunking, indexing, and Celery tasks; `rag/retrieval.py` holds scoped search, rank fusion, and reranking steps; `rag/providers/` holds Jina clients |
| `evals/` (in `src/app/evals/`) | Pure scoring of retrieval results against expected pages, used by the runners in `evals/` |
| `search/` | OpenSearch index mapping and bulk indexing |
| `schema/` | Every Pydantic request, response, and provider payload model (`models.py`) |
| `config/` | Settings read from environment variables and `.env`, including `Settings.is_cloud` |
| `workers/` | Celery worker app |
| `db/` | PostgreSQL migration runner, the per-request connection dependency (`db/connection.py`), and database queries for conversations (`db/conversations.py`) |
| `storage/` | Original-file storage adapters, including the `get_storage` dependency |
| `observability/` | Structured JSON logging |
| `api/main.py` request IDs | Accept only letters, digits, `-`, and `_` up to 64 characters; otherwise generate one |

## Upload and indexing API

A new upload starts indexing as part of the same user action. After the original is durably stored and the upload is finalized, the browser automatically calls the ingest endpoint. FastAPI records the document with its pinned source and queues a job. The worker extracts text, chunks it, generates embeddings, and stores the vectors in the index. FastAPI validates file type, size, and malware status before the upload is finalized. The browser shows per-file job progress. A file whose original could not be stored is reported as failed before any indexing job is queued.

Document status moves through `queued`, `processing`, then `ready` or `failed`. Only `ready` documents are searchable. A failed job records a safe error for the file registry.

Reingestion is a separate action for an existing document, such as after a transcript correction or a change to chunking settings. It reads the recorded original from storage and reuses processing results that are still valid.

| Operation | Contract |
|---|---|
| Upload initialization | Browser sends size and SHA-256. Require write access to the destination collection. Offer reuse only for a verified match the caller can currently read in the same workspace. For every other request, issue the usual resumable upload session and verify bytes and size server-side. |
| `POST /collections/{collection_id}/documents/ingest` | Starts first-time indexing for one or more finalized upload IDs. Accepts an idempotency key and returns HTTP 202 with the per-document job IDs. |
| `POST /collections/{collection_id}/documents/{document_id}/reingest` | Accepts an idempotency key and optional approved extraction, chunking, or enrichment settings compatible with the active collection embedding profile. Reads the recorded raw object generation and returns HTTP 202 with a job ID. Direct model changes to collection settings. A repeat can complete as a no-op. |
| Collection settings update | An authorized change to the target embedding profile starts a collection-wide migration and returns its job ID. The settings view shows progress, failure, or activation using the job status API. |
| `GET /collections/{collection_id}/jobs/{job_id}` | Returns authorized job status, stage, and safe failure information. |
| `POST /collections/{collection_id}/chat/stream` | Creates a conversation on the first turn and returns its ID. Follow-ups provide that conversation ID. Streams server-sent events: `conversation` (ID), `delta` (answer text), then `done` (message ID, final answer, validated citations with passage text) or `error` (safe message). A turn is saved only when its citations are valid. Optional structured results and chart data come later. |
| `GET /collections/{collection_id}/conversations`, `.../conversations/{conversation_id}` | Lists saved conversations with messages, in order, including citations. |
| `GET /collections/{collection_id}/documents/{document_id}/original` | Returns the stored original PDF for the source viewer. Opens at the cited page (`#page=N`). |

Keep raw uploads durable before queuing work. A document points to an immutable bucket object generation and records its original UTC upload time. Recheck source read and destination write permissions when linking a reused upload. A hash match against an inaccessible source follows the same client-visible flow as a new upload. After independently verifying the uploaded bytes, storage may deduplicate internally. Shared objects keep separate document permissions. Maintain a reference count or derive references transactionally before cleaning up objects. Check authorization again when a source is opened. Use provisional quotas of 500 MB per collection and 10 URLs when URL ingestion launches. Reserve upload capacity transactionally and expire unused reservations.

## Ingestion and reuse

1. Validate content type and resource limits in a worker. Extract text and layout from supported files. Preserve page regions, or sheet and row coordinates for structured data.
2. Use Docling with RapidOCR and table structure enabled for PDF parsing and printed scans. Prefer embedded text where usable. Retry full-page OCR for pages with missing or broken text layers. Route user-marked handwriting pages to Document AI and normalize the result to the same page format. Record uncertain spans and support reviewed transcript corrections.
3. Create deterministic LlamaIndex nodes. Store `SOURCE`, `PREVIOUS`, and `NEXT` links and verify cross-page links. Add `PARENT` and `CHILD` links when evaluation shows a recurring need for larger context. Store authoritative title, headings, source location, upload time, extraction method, and access scope. Keep operational IDs and upload time out of model and embedding text.
4. Start with title, heading, and source text. Trial one generated enrichment at a time, beginning with one or two questions each chunk can answer. Use those questions as retrieval input and cite the original passage. 
   Graph RAG is on by default. A worker stage extracts entities and relationships from every document and writes them to the graph store with the document and workspace scope. It then builds document-level and collection-level summaries from that graph, so summary questions have material to answer from. Extraction and summary calls are cached by enrichment identity and claimed with leases. A document becomes `ready` only after its graph writes are verified.
5. Stage the OpenSearch index under a versioned name. Verify that all bulk writes succeeded and are searchable before publishing the active index pointer in PostgreSQL. Keep the previous serving index available throughout the build.

| Identity | Reuse rule |
|---|---|
| Raw blob | Workspace plus verified file hash. Bucket object generation identifies the exact bytes. |
| Parsed artifact | Workspace, file hash, and extraction profile, including parser and OCR versions, language, settings, and any transcript revision. For page artifacts also include page identity. |
| Chunk ID | Document ID, canonical source locator, and hash of normalized source text. Repeated text at different locations has distinct IDs. |
| Enrichment | Workspace and hash of the exact enrichment input, prompt, and model profile. |
| Embedding | Workspace, hash of the exact embedding input, and embedding profile including model version, dimensions, and document embedding settings. |
| Index membership | An indexing run records active chunk versions, relationships, citation metadata, and keyword search data. It can reference existing vectors. |

Selecting the same authorized file again in the browser can transfer zero file bytes. Reingesting a document by ID reads its stored source. With the same profile and complete cached artifacts, reingestion makes zero new OCR, enrichment, or embedding calls. A chunking change can reuse parsed pages. A generation model, answer prompt, or reranker change applies at query time.

Before calling an OCR, enrichment, or embedding provider, atomically claim the artifact key in PostgreSQL using a renewable lease. Return a completed artifact immediately. If another worker holds a valid lease, wait or reschedule and read its result. Only the current lease holder can publish the result. After expiry, a new holder can retry. Send the same provider idempotency key on retries where supported. If a worker dies after the provider charges but before it persists the result, recovery can incur another charge.

When the target embedding profile changes in collection settings, stage vectors in an index sized for that profile. Continue serving the active index while the migration incorporates documents added, reingested, or deleted during the build. Check the collection revision at activation and catch up if it has advanced. Switch the active OpenSearch index name and query embedding profile together in one PostgreSQL transaction. A failed migration leaves the existing pair active. Pin each chat request to its starting index and profile. Preserve prior published citation coordinates while the associated sources remain authorized.

Write the job and an outbox entry in one database transaction. The publisher may deliver a job more than once. Enforce uniqueness on artifact keys and index membership, and use bounded attempts, job leases, and a reconciler for expired work. Fence index activation so a stale run cannot overwrite a newer run or revive a deleted document. Document deletion revokes retrieval and source access immediately, then schedules cleanup. Check candidate document access and deletion state against PostgreSQL before using OpenSearch hits as evidence.

## Conversation memory

Authorize the conversation, caller, workspace, and collection before reading any turns. PostgreSQL stores the ordered transcript. After a turn commits, cache recent turns in Redis under the workspace, collection, and conversation IDs with a configurable expiry. Check the cached transcript revision against the latest committed turn. On expiry, eviction, stale data, or Redis failure, load the same recent turns from PostgreSQL. Recheck access to prior source evidence before using it in a follow-up.

## Retrieval, vision, and citations

Query flow: FastAPI authenticates the caller and checks the conversation's workspace and collection. Query preparation loads recent turns and rewrites a follow-up only when needed, keeping the original question. Every query runs three retrieval branches in parallel with the same access filters: keyword (BM25), vector search, and graph retrieval over the entity graph and the summaries built at ingest. No classifier chooses a route. Results from all branches are merged with reciprocal rank fusion, deduplicated, and reranked with a cross-encoder, so the reranker decides which evidence matters. Graph retrieval is what lets summary questions succeed, since no single chunk holds the whole document. Chunks are selected within a token budget, with authorized neighbors added where useful. If no relevant evidence remains, the answer says it was not found. Otherwise prompt assembly keeps evidence separate from instructions, the LLM call is guarded by cost limits and prompt-injection checks, and citations are validated. The response includes a `trace_id`. Only `ready` documents are searched.

Use filtered exact k-NN search over OpenSearch `knn_vector` fields as the initial baseline. Add OpenSearch BM25 keyword search with the same workspace, collection, and document access filters, fuse ranks with reciprocal rank fusion, and rerank candidate passages against the user question. Start by retrieving 20 candidates per branch, reranking up to 20 unique chunks, and building an evidence context of roughly 5–8 passages. Tune against evaluated corpus sizes. Expand to authorized neighboring nodes only where the answer needs them. Treat extracted content as untrusted evidence and keep it separate from application instructions.

Validate citation IDs against the supplied evidence and authorize the source when opening it. For chart, diagram, or ambiguous handwriting questions, a bounded vision step can view selected page images or crops. If a critical value remains unclear, surface the uncertainty. Evaluate ColPali as a page-image retrieval branch if visual pages regularly miss the candidate set. Benchmark page recall, latency, and index cost before adopting it.

## Structured calculations

Normalize CSV and XLSX sheets into typed, versioned datasets. Store column types, units, currency, source rows, and import warnings. Index a short dataset description in LlamaIndex for discovery. Admit PDF or handwritten tables to calculation only after validating the relevant rows and columns.

A validated analysis request pins an authorized dataset version and specifies the operation, measure, group-by columns, typed filters, and optional time comparison. Use a bounded set of operations and backend-generated, parameterized read-only SQL. Validate identifiers against that version's schema and apply execution time and result limits. Compute over all matching rows using decimal arithmetic for monetary values.

Import blank numeric cells as null and preserve explicit zeroes. For sums and averages, report missing-value counts and return an unavailable result when all matching values are null. Preserve duplicate rows unless the request specifies a deduplication rule. Ask for the intended unit, currency, or period when aggregation is ambiguous. If a required formula value is missing or known to be stale, explain which cells need a recalculated value and withhold the affected calculation. When no eligible dataset exists, ask for the structured source needed to answer.

For combined questions, compute the result first and retrieve relevant explanations second. Return structured results, applied filters, units, and dataset version. Render charts from those values and cite the same dataset version with sheet and row provenance. Cite document pages for narrative evidence.

## Observability and evaluation

Rollout is staged. Each stage builds on the previous one.

1. **Logging (now):** structlog writes JSON logs to container stdout from FastAPI and Celery. Each line carries `request_id`, plus `job_id` or `conversation_id` where relevant. Never log raw document text, private chats, or credentials.
2. **Celery monitoring (now):** Flower runs privately in Compose and shows workers, queues, tasks, and retries. Enable worker events.
3. **Metrics (next):** Prometheus scrapes FastAPI and worker metrics. Grafana shows request count, errors, latency, queue age, retries, job outcomes, and cache hits. Keep document and user IDs out of metric labels.
4. **Tracing and cloud (later):** OpenTelemetry spans across FastAPI and Celery, with trace IDs attached to logs. For GKE, `APP_MODE=cloud` exports to Cloud Monitoring, Cloud Logging, and Cloud Trace.
5. **LLM inspection (later):** LangSmith or Langfuse for model and retrieval traces. Default to redacted inputs and outputs. Keep raw document text, private chats, and credentials out of traces.
- Use versioned Ragas cases and record retrieved IDs and passages, expected pages, reference answers, and actual output. Measure retrieval recall and precision, faithfulness, and response relevance. Test citation authorization and numeric correctness with deterministic assertions. Track handwriting transcription accuracy, visual page recall, and cache reuse separately.

## References

- [OpenSearch exact k-NN search](https://docs.opensearch.org/latest/vector-search/vector-search-techniques/knn-score-script/)
- [OpenSearch BM25 similarity](https://docs.opensearch.org/latest/mappings/mapping-parameters/similarity/)
- [Docling OCR configuration](https://github.com/docling-project/docling/blob/main/docling/datamodel/pipeline_options.py)
- [Google Document AI Enterprise OCR](https://docs.cloud.google.com/document-ai/docs/enterprise-document-ocr)
- [ColPali paper](https://arxiv.org/html/2407.01449v4)
- [Ragas metrics](https://docs.ragas.io/en/stable/concepts/metrics/available_metrics/)
- [LangSmith trace privacy controls](https://docs.langchain.com/langsmith/mask-inputs-outputs)
