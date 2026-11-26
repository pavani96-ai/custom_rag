COMPOSE = docker compose --env-file .env -f ops/compose.yaml
export DOCUMENT_ID
PDF ?= docs/demo-docs/Transformer_Theory_Notes.pdf
export PDF
QUERY ?= What is deep learning, and how do neurons in a neural network pass information to each other?
TOP_K ?= 5
COLLECTION_ID ?= 00000000-0000-4000-8000-000000000003
export QUERY TOP_K COLLECTION_ID
export EVAL_UID := $(shell id -u)
export EVAL_GID := $(shell id -g)
EVAL_LIMIT ?= 0
EVAL_QUESTIONS_PER_PAGE ?= 2
EVAL_DATASET ?= taxonomy.json
EVAL_REPORT ?= taxonomy-report.json
EVAL_PDF ?= Data Taxonomy & Annotation Guide (1).pdf
export EVAL_DATASET EVAL_REPORT EVAL_PDF

.PHONY: env up down migrate logs document-status demo-ingest demo-search demo-ask eval-build eval-dataset eval-run check

# Create .env from the template once, then edit the placeholder values.
env:
	@test -f .env || cp .env.example .env
	@echo "Edit .env and set POSTGRES_PASSWORD."

up: env
	$(COMPOSE) up -d --build
	$(MAKE) migrate

# Apply pending SQL migrations inside the API container. Safe to run repeatedly.
migrate:
	$(COMPOSE) exec -T api python -m app.db.migrate

down:
	$(COMPOSE) down

logs:
	$(COMPOSE) logs -f api worker

document-status:
	@test -n "$$DOCUMENT_ID" || { echo "Usage: make document-status DOCUMENT_ID=<document UUID>" >&2; exit 2; }
	@echo "SELECT filename, status FROM documents WHERE id = :'document_id'::uuid;" | \
		$(COMPOSE) exec -T postgres psql -X -U rag -d rag \
		-v ON_ERROR_STOP=1 -v document_id="$$DOCUMENT_ID"

demo-ingest:
	@python3 ops/demo_ingest.py "$$PDF" $(COMPOSE)

demo-search demo-ask:
	@payload=$$(python3 -c 'import json, os; print(json.dumps({"query": os.environ["QUERY"], "top_k": int(os.environ["TOP_K"])}))') && \
		curl --silent --show-error --fail-with-body --write-out '\n' \
		--header 'Content-Type: application/json' --data "$$payload" \
		"http://localhost:8000/collections/$$COLLECTION_ID/$(patsubst demo-%,%,$@)"

eval-build:
	docker build -f ops/api.Dockerfile --target eval -t rag-eval:local src

eval-dataset: eval-build
	@mkdir -p evals
	$(COMPOSE) run --rm --no-deps eval generate "/inputs/$$EVAL_PDF" \
		"/evals/$$EVAL_DATASET" --questions-per-page $(EVAL_QUESTIONS_PER_PAGE)

eval-run: eval-build
	$(COMPOSE) run --rm --no-deps eval score "/evals/$$EVAL_DATASET" \
		"/evals/$$EVAL_REPORT" --collection-id "$$COLLECTION_ID" \
		--top-k "$$TOP_K" --limit $(EVAL_LIMIT)

# Runs lint and tests for the API and the web type check and build, all in Docker.
check:
	docker build -f ops/api.Dockerfile --target test -t rag-api-test src
	docker build --target build -t rag-web-build apps/web
