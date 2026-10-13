# OpsPilot root automation. Targets are added as each phase lands;
# see DEVELOPMENT_PLAN.md §10.4 for the full list.

SHELL := /bin/bash
.DEFAULT_GOAL := help

-include .env
export

COMPOSE := docker compose
API := cd apps/api && uv run

.PHONY: help infra-up infra-down stop secrets-scan install api-dev format lint typecheck test test-unit test-integration

help: ## List available targets
	@grep -hE '^[a-zA-Z_-]+:.*?## ' $(MAKEFILE_LIST) | sort | \
		awk 'BEGIN {FS = ":.*?## "}; {printf "  \033[36m%-18s\033[0m %s\n", $$1, $$2}'

infra-up: ## Start PostgreSQL and Redis and wait until healthy
	$(COMPOSE) up -d --wait postgres redis

infra-down: ## Stop PostgreSQL and Redis (keeps data)
	$(COMPOSE) down

stop: infra-down ## Stop everything started by make dev

secrets-scan: ## Scan the working tree and history for secrets
	gitleaks detect --no-banner --redact

install: ## Install all dependencies
	cd apps/api && uv sync --frozen

api-dev: ## Run the API with auto-reload against local infra
	cd apps/api && uv run uvicorn opspilot_api.main:create_app --factory --reload \
		--host 127.0.0.1 --port $${API_PORT:-8000} --no-access-log

format: ## Format all code
	$(API) ruff format .
	$(API) ruff check --fix .

lint: ## Lint all code (no changes)
	$(API) ruff format --check .
	$(API) ruff check .

typecheck: ## Static type checks
	$(API) mypy

test: test-unit ## Fast tests (unit)

test-unit: ## Unit tests
	$(API) pytest tests/unit

test-integration: ## Integration tests against real containers (needs Docker)
	$(API) pytest tests/integration
