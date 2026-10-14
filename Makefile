# OpsPilot root automation. Targets are added as each phase lands;
# `make help` lists them.

SHELL := /bin/bash
.DEFAULT_GOAL := help

-include .env
export

COMPOSE := docker compose
# The local cluster gets its own kubeconfig so other clusters are never touched.
KUBECONFIG := $(CURDIR)/.kube/config
KUBECTL := kubectl --context kind-opspilot
HELM := helm --kube-context kind-opspilot
DEMO_IMAGE := opspilot-demo:dev
API := cd apps/api && uv run
DEMO := cd demo/services && uv run

.PHONY: db-upgrade db-downgrade db-revision keycloak-smoke token api-client web-dev dev build test-e2e test-lighthouse kind-create kind-delete docker-build deploy-local observability-up load-normal load-stop inject-failure reset-demo seed seed-runbooks test-telemetry test-detection worker help infra-up infra-down llm-up stop secrets-scan install api-dev format lint typecheck test test-unit test-integration

help: ## List available targets
	@grep -hE '^[a-zA-Z_-]+:.*?## ' $(MAKEFILE_LIST) | sort | \
		awk 'BEGIN {FS = ":.*?## "}; {printf "  \033[36m%-18s\033[0m %s\n", $$1, $$2}'

infra-up: ## Start PostgreSQL, Redis, and Keycloak and wait until healthy
	$(COMPOSE) up -d --wait postgres redis keycloak

llm-up: ## Start the local LLM (Ollama, GPU when available) and pull the agent model
	$(COMPOSE) --profile llm up -d --wait ollama
	$(COMPOSE) exec ollama ollama pull $${LLM_MODEL:-qwen2.5:7b-instruct}

infra-down: ## Stop local infrastructure (keeps data)
	$(COMPOSE) down

stop: infra-down ## Stop everything started by make dev

secrets-scan: ## Scan the working tree and history for secrets
	gitleaks detect --no-banner --redact

install: ## Install all dependencies
	cd apps/api && uv sync --frozen
	cd demo/services && uv sync --frozen
	pnpm install --frozen-lockfile

api-dev: ## Run the API with auto-reload against local infra
	cd apps/api && uv run uvicorn opspilot_api.main:create_app --factory --reload \
		--host 127.0.0.1 --port $${API_PORT:-8000} --no-access-log --no-proxy-headers

format: ## Format all code
	$(API) ruff format .
	$(API) ruff check --fix .
	$(DEMO) ruff format .
	$(DEMO) ruff check --fix .
	pnpm --filter @opspilot/web exec eslint --fix

lint: ## Lint all code (no changes)
	$(API) ruff format --check .
	$(API) ruff check .
	$(DEMO) ruff format --check .
	$(DEMO) ruff check .
	pnpm --filter @opspilot/web lint

typecheck: ## Static type checks
	$(API) mypy
	$(DEMO) mypy
	pnpm --filter @opspilot/api-client typecheck
	pnpm --filter @opspilot/web typecheck

test: test-unit ## Fast tests (unit)

test-unit: ## Unit tests
	$(API) pytest tests/unit
	$(DEMO) pytest
	pnpm --filter @opspilot/web test

test-integration: ## Integration tests against real containers (needs Docker)
	$(API) pytest tests/integration

api-client: ## Regenerate the typed API client from the API's OpenAPI schema
	cd apps/api && uv run python -c "import json; from opspilot_api.config import Settings; \
		from opspilot_api.main import create_app; \
		print(json.dumps(create_app(Settings()).openapi(), indent=2))" > ../../packages/api-client/openapi.json
	pnpm --filter @opspilot/api-client generate

worker: ## Run the detection worker against local infra and the kind cluster's Prometheus
	cd apps/api && uv run opspilot-worker

web-dev: ## Run the web app with hot reload (proxies /api/v1 to the API)
	API_URL=http://127.0.0.1:$${API_PORT:-8000} OIDC_ISSUER=$${JWT_ISSUER} \
		pnpm --filter @opspilot/web dev --port $${WEB_PORT:-3000}

dev: infra-up db-upgrade ## Start infrastructure, migrate, and run API and web together
	@trap 'kill 0' INT TERM EXIT; $(MAKE) --no-print-directory api-dev & $(MAKE) --no-print-directory web-dev & \
		$(if $(PROMETHEUS_URL),$(MAKE) --no-print-directory worker &,) wait

build: ## Production build of all apps
	cd apps/api && uv build -q
	@# Build without runtime settings, as CI does: nothing may need them at build time.
	env -u API_URL -u REDIS_URL -u OIDC_ISSUER -u OIDC_CLIENT_ID -u OIDC_CLIENT_SECRET \
		pnpm --filter @opspilot/web build

test-e2e: infra-up db-upgrade ## Browser tests against the real stack (Playwright)
	pnpm exec playwright test

test-lighthouse: infra-up db-upgrade ## Lighthouse budgets on primary pages (production build); summary in test-results/lighthouse
	pnpm exec playwright test --config playwright.lighthouse.config.ts

keycloak-smoke: ## Check every dev user gets a token with roles, organization, and API audience
	./scripts/keycloak-smoke.sh

token: ## Print a dev access token: make token USER=commander
	@./scripts/dev-token.sh $(USER)

db-upgrade: ## Apply all database migrations
	$(API) python -m opspilot_api.db upgrade head

db-downgrade: ## Roll back the last database migration
	$(API) python -m opspilot_api.db downgrade -1

db-revision: ## Autogenerate a migration: make db-revision MSG="add incidents"
	$(API) python -m opspilot_api.db revision --autogenerate -m "$(MSG)"

kind-create: ## Create the local kind cluster (kubeconfig in .kube/config)
	@kind get clusters 2>/dev/null | grep -qx opspilot || kind create cluster --config infrastructure/kind/cluster.yaml --kubeconfig $(KUBECONFIG)

kind-delete: ## Delete the local kind cluster
	kind delete cluster --name opspilot --kubeconfig $(KUBECONFIG)

docker-build: ## Build the demo image and load it into the kind cluster
	docker build -q -t $(DEMO_IMAGE) demo/services
	kind load docker-image $(DEMO_IMAGE) --name opspilot

observability-up: kind-create ## Deploy the collector, Prometheus, Loki, Tempo, and Grafana to the kind cluster
	$(KUBECTL) apply -f observability/k8s/namespace.yaml
	@$(KUBECTL) -n observability get secret grafana-admin >/dev/null 2>&1 || \
		$(KUBECTL) -n observability create secret generic grafana-admin --from-literal=password="$$(openssl rand -hex 16)"
	$(KUBECTL) apply -k observability/k8s
	$(KUBECTL) -n observability rollout status deploy,daemonset --timeout=5m

deploy-local: observability-up docker-build ## Deploy observability and the demo shop to the kind cluster
	$(HELM) upgrade --install demo-shop infrastructure/helm/demo-shop --namespace demo --create-namespace --wait --timeout 5m

load-normal: ## Start steady synthetic traffic against the demo shop (RPS=5)
	$(HELM) upgrade demo-shop infrastructure/helm/demo-shop --namespace demo --reuse-values \
		--set loadgen.enabled=true --set loadgen.rps=$${RPS:-5} --wait

load-stop: ## Stop the synthetic traffic
	$(HELM) upgrade demo-shop infrastructure/helm/demo-shop --namespace demo --reuse-values \
		--set loadgen.enabled=false --wait

inject-failure: ## Ship a faulty release: make inject-failure SCENARIO=checkout-http-500
	./scripts/inject-failure.sh $(SCENARIO)

reset-demo: ## Restore every demo service to its healthy release (keeps load running)
	$(KUBECTL) -n demo annotate deployment --all --overwrite kubernetes.io/change-cause="reset to the healthy release"
	$(HELM) upgrade demo-shop infrastructure/helm/demo-shop --namespace demo --reuse-values --force-conflicts --wait

seed: ## Register the demo shop in the service catalog (API must be running)
	cd apps/api && uv run python -m opspilot_api.demo_seed \
		--api-url http://127.0.0.1:$${API_PORT:-8000} --token "$$(../../scripts/dev-token.sh admin)"

seed-runbooks: ## Load docs/runbooks into the runbook library (API must be running)
	cd apps/api && uv run python -m opspilot_api.runbook_seed \
		--api-url http://127.0.0.1:$${API_PORT:-8000} --token "$$(../../scripts/dev-token.sh admin)"

test-detection: ## One sustained failure → exactly one incident, with detection delay (needs make dev and the kind stack)
	cd demo/services && uv run python -u ../../tests/telemetry/detection_smoke.py

test-telemetry: ## Follow one request through traces, logs, and metrics on the kind cluster
	cd demo/services && uv run python -u ../../tests/telemetry/telemetry_smoke.py

