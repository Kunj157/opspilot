# OpsPilot

An AI-assisted Site Reliability Engineering platform that detects cloud
application incidents, investigates them with AI agents and ML, proposes safe
remediation, executes human-approved runbooks, verifies recovery, and writes
postmortems.

> Status: Phase 1 — local development foundation.

- [Development plan](DEVELOPMENT_PLAN.md) — what is being built and in which order
- [Development workflow](DEVELOPMENT_WORKFLOW.md) — how every change is made

The full README (demo, screenshots, setup, results) is a Phase 0–13
deliverable; see `DEVELOPMENT_PLAN.md` §30.

## Local development

Requirements: Docker, Node 22 with pnpm (via corepack), Python 3.12 with
[uv](https://docs.astral.sh/uv/), make.

```bash
cp .env.example .env      # adjust ports if 5432/6379/8000/3000 are taken
make install
make dev                  # PostgreSQL, Redis, API, and web; Ctrl+C stops all
```

Open http://localhost:3000 for the web app; the API's readiness is at
http://localhost:8000/api/v1/ready.

| Command | What it does |
|---|---|
| `make lint` / `make format` | ruff + eslint |
| `make typecheck` | mypy (strict) + tsc |
| `make test` | API and web unit tests |
| `make test-integration` | API tests against real containers (Testcontainers) |
| `make test-e2e` | Playwright against the full stack |
| `make api-client` | Regenerate the typed client from the API's OpenAPI schema |
| `make secrets-scan` | gitleaks |

`make help` lists everything.
