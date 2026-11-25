COMPOSE = docker compose --env-file .env -f ops/compose.yaml

.PHONY: env up down logs check

# Create .env from the template once, then edit the placeholder values.
env:
	@test -f .env || cp .env.example .env
	@echo "Edit .env and set POSTGRES_PASSWORD."

up: env
	$(COMPOSE) up -d --build

down:
	$(COMPOSE) down

logs:
	$(COMPOSE) logs -f api worker

# Runs lint and tests for the API and the web type check and build, all in Docker.
check:
	docker build --target test -t rag-api-test services/api
	docker build --target build -t rag-web-build apps/web
