# Document intelligence workspace

A planned Google Cloud application for asking questions across private files and calculating results from spreadsheets. Document answers link to source pages. Calculations link to the dataset version, sheet, and rows behind each number.

Read each diagram one row at a time, from left to right. Each row follows one operation or signal.

## System map

![Four left-to-right paths show how the workspace uploads files, queues indexing, answers questions, and stores conversation history.](docs/diagrams/system-map.png)

The browser uploads new files directly to Cloud Storage after FastAPI authorizes the destination. Reingestion starts from a stored document ID. On a Redis cache miss, FastAPI reloads the authorized conversation from PostgreSQL.

<details>
<summary>Editable Mermaid flow</summary>

```mermaid
flowchart LR
    accTitle: How the workspace fits together
    accDescr: Four left-to-right paths show how the workspace uploads files, queues indexing, answers questions, and stores conversation history.
    n11["FastAPI<br/>Authorize upload to<br/>the collection"] --> n12["Next.js browser<br/>Send file bytes<br/>directly to the bucket"] --> n13["Cloud Storage<br/>Keep the original<br/>at a pinned version"]
    n21["PostgreSQL outbox<br/>FastAPI records the job<br/>with the outbox entry"] --> n22["Redis broker<br/>The outbox publisher<br/>delivers the job"] --> n23["Celery worker<br/>Read the original and<br/>build the index"]
    n31["Next.js chat<br/>Send the question<br/>and conversation ID"] --> n32["FastAPI<br/>Run retrieval, SQL,<br/>or both"] --> n33["Next.js chat<br/>Show the answer with<br/>citations or a chart"]
    n41["FastAPI<br/>Commit the<br/>completed turn"] --> n42["PostgreSQL<br/>Store the ordered<br/>conversation history"] --> n43["Redis cache<br/>Keep recent turns<br/>until expiry"]
    classDef result fill:#E3F3EF,stroke:#135E5B,color:#172B38
    class n13,n23,n33,n43 result
```

</details>

## How a file becomes searchable

Celery runs these paths. Printed and handwritten extraction feed the indexing row. LlamaIndex also indexes spreadsheet descriptions for discovery. A worker claims each missing artifact in PostgreSQL before requesting paid processing. Reingestion reuses completed OCR, enrichment, and embeddings. Generated chunk questions are the first enrichment experiment. A change to the embedding model triggers a collection-wide index migration.

```mermaid
flowchart LR
    accTitle: From source file to index
    accDescr: Printed and handwritten pages become cached page text. A third row turns that text into linked vector-searchable chunks. Spreadsheet rows follow a typed import into PostgreSQL.
    n11["Cloud Storage<br/>Read PDF pages<br/>or printed scans"] --> n12["Docling + RapidOCR<br/>Extract native text,<br/>layout, or OCR text"] --> n13["Cloud Storage<br/>Cache parsed pages<br/>and source locations"]
    n21["Cloud Storage<br/>Read pages marked<br/>as handwritten"] --> n22["Google Document AI<br/>Recognize handwriting<br/>and retain coordinates"] --> n23["Cloud Storage<br/>Cache the transcript<br/>and page references"]
    n31["LlamaIndex<br/>Link stable chunks<br/>to their source pages"] --> n32["Vertex AI<br/>Compute embeddings<br/>on cache misses"] --> n33["OpenSearch<br/>Publish chunks, vectors,<br/>and keyword search data"]
    n41["CSV or XLSX<br/>Read sheets and<br/>original row positions"] --> n42["Typed table import<br/>Validate columns,<br/>units, and provenance"] --> n43["PostgreSQL<br/>Store versioned rows<br/>for exact calculations"]
    classDef result fill:#E5F1F9,stroke:#175B84,color:#172B38
    class n13,n23,n33,n43 result
```

## How a question becomes an answer

FastAPI checks collection and conversation access before querying. Vertex AI embeds the question for OpenSearch vector search. For a mixed question it calculates first, then uses the result to find explanatory passages. For visual questions it can send a retrieved page or crop to a vision model. ColPali is a retrieval experiment if visual pages regularly miss the candidate set.

```mermaid
flowchart LR
    accTitle: Find evidence or calculate a result
    accDescr: Document search finds evidence for generation, optional vision reads a retrieved page, and read-only SQL computes results over all eligible rows.
    n11["Authorized question<br/>Search the active<br/>collection index"] --> n12["Hybrid retrieval<br/>OpenSearch vector search +<br/>BM25 keyword search"] --> n13["LlamaIndex<br/>Fuse ranks and rerank<br/>the source passages"]
    n21["Retrieved page<br/>Select the chart,<br/>diagram, or form crop"] --> n22["Vision model<br/>Read the detail from<br/>the selected region"] --> n23["Page evidence<br/>Carry the original<br/>page citation forward"]
    n31["Ranked evidence<br/>Use passages and any<br/>selected visual evidence"] --> n32["Vertex AI<br/>Generate an answer<br/>grounded in the sources"] --> n33["FastAPI → Next.js<br/>Validate citation IDs<br/>and display the answer"]
    n41["Dataset version<br/>Pin the authorized<br/>rows and filters"] --> n42["Read-only SQL<br/>PostgreSQL aggregates<br/>all matching rows"] --> n43["Next.js<br/>Display exact values,<br/>chart, and sheet citation"]
    classDef result fill:#EFEBF8,stroke:#5B4A85,color:#172B38
    class n13,n23,n33,n43 result
```

## Monitoring and evaluation

With `APP_MODE=local`, Grafana reads application metrics and metrics derived from trace spans from Prometheus. With `APP_MODE=cloud`, OpenTelemetry exports metrics to Cloud Monitoring, logs to Cloud Logging, and spans to Cloud Trace. Trace IDs correlate cloud logs and spans. Ragas runs in CI and on a schedule.

```mermaid
flowchart LR
    accTitle: Telemetry routing by application mode
    accDescr: Local metrics feed Prometheus and Grafana. Cloud telemetry goes to Google Cloud Observability.
    n11["Local app metrics<br/>and trace spans"] --> n12["OpenTelemetry Collector<br/>Derive metrics from spans"] --> n13["Prometheus"] --> n14["Grafana"]
    n21["Cloud app metrics,<br/>logs, and trace spans"] --> n22["OpenTelemetry Collector"]
    n22 --> n23["Cloud Monitoring<br/>Metrics and alerts"]
    n22 --> n24["Cloud Logging<br/>Structured logs"]
    n22 --> n25["Cloud Trace<br/>Request and worker spans"]
    n41["Celery workers<br/>Task lifecycle events"] --> n42["Redis broker<br/>Carry Celery events"] --> n43["Flower<br/>Inspect private worker<br/>and task dashboards"]
    n51["Retrieval + generation<br/>Model and retrieval runs"] --> n52["Trace redaction<br/>Remove sensitive inputs<br/>and outputs"] --> n53["LangSmith<br/>Inspect traced runs"]
    n61["Evaluation cases<br/>Reference answers and<br/>retrieved passages"] --> n62["Ragas<br/>Score retrieval and<br/>answer faithfulness"] --> n63["Quality reports<br/>Review CI and<br/>scheduled results"]
    classDef result fill:#FBF0DE,stroke:#865019,color:#172B38
    class n14,n23,n24,n25,n43,n53,n63 result
```

## From local development to Google Cloud

![Five paths cover Docker Compose, Terraform provisioning, image publishing, GKE deployment, and workload access to Secret Manager.](docs/diagrams/deployment.png)

Kubernetes manifests deploy Next.js, FastAPI, Celery, the outbox publisher, and operational services. Cloud SQL hosts PostgreSQL. A private OpenSearch workload on GKE serves vector and keyword queries. Memorystore provides separate Redis broker and cache capacity. Workload Identity gives services access to Cloud Storage and Secret Manager. Later source integrations include URLs, Google Drive, OneDrive, and SharePoint.

<details>
<summary>Editable Mermaid flow</summary>

```mermaid
flowchart LR
    accTitle: Build, release, and run
    accDescr: Five paths cover Docker Compose, Terraform provisioning, image publishing, GKE deployment, and workload access to Secret Manager.
    n11["Docker images<br/>Web, API, and workers"] --> n12["Docker Compose<br/>Start the local stack"] --> n13["Local workspace<br/>App, stores, workers,<br/>and monitoring"]
    n21["Terraform<br/>Versioned infrastructure<br/>definitions"] --> n22["Google Cloud<br/>Provision the VPC, GKE,<br/>storage, and identities"] --> n23["Managed services<br/>Cloud SQL, Memorystore,<br/>and Cloud Storage"]
    n31["Application code<br/>Versioned source<br/>and Dockerfiles"] --> n32["CI/CD<br/>Test, evaluate, and<br/>build Docker images"] --> n33["Artifact Registry<br/>Store immutable<br/>release images"]
    n41["Release images<br/>Select the tested<br/>image versions"] --> n42["GKE staging<br/>Apply manifests and<br/>verify the full workflow"] --> n43["GKE production<br/>Promote the same<br/>verified images"]
    n51["GKE workloads<br/>Run the application<br/>under service accounts"] --> n52["Workload Identity<br/>Authenticate each<br/>workload to Google Cloud"] --> n53["Secret Manager<br/>Read the secrets this<br/>workload may access"]
    classDef result fill:#E8F0F5,stroke:#375A75,color:#172B38
    class n13,n23,n33,n43,n53 result
```

</details>

[Architecture and API contracts](docs/architecture.md) · [Implementation milestones and acceptance checks](docs/plan.md)
