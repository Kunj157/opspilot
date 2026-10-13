# OpsPilot root automation. Targets are added as each phase lands;
# see DEVELOPMENT_PLAN.md §10.4 for the full list.

SHELL := /bin/bash
.DEFAULT_GOAL := help

-include .env
export

COMPOSE := docker compose

.PHONY: help infra-up infra-down stop secrets-scan

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
