# Development Workflow — Solo Developer (Kunj157)

Solo-developer GitHub workflow, commit/authorship rules, and the headless
iterative testing loop for OpsPilot (Next.js + FastAPI + workers + ML +
Kubernetes). Applies to every task in this repo, for humans and agents alike.

This is a **one-person project**. There is no team, no reviewer, no approver.
Every rule below is written for a single developer who is also their own
reviewer. Follow it on every task, without being asked.

`DEVELOPMENT_PLAN.md` says **what** to build and in which order. This file
says **how** every change gets made. If the two disagree on process, this file
wins; if they disagree on scope, the plan wins.

---

## 0. Non-negotiables (read first)

1. **Never commit directly to `main` or `dev`.** All work happens on a
   `feature/*`, `bugfix/*`, `infra/*`, `docs/*`, `release/*`, or `hotfix/*`
   branch. The only exception is the one-time repository bootstrap commit
   (§1.1).
2. **Never add a co-author.** No `Co-Authored-By:` trailer for Cursor, Claude,
   Copilot, ChatGPT, or any other tool or person. No "Generated with …" footer.
   No AI attribution anywhere in the commit message, PR title, or PR body.
   The sole author of every commit is **Kunj157 `<kunjr157@gmail.com>`**.
3. **Never ship untested behavior.** Every API endpoint, worker flow, and UI
   flow is driven by an automated test — pytest for the backend, Vitest for
   components, Playwright (via the Playwright MCP server while iterating) for
   browser flows — run headless and iterated on until correct, before the PR
   is opened (§6).
4. **Never commit secrets.** No real values in `.env*` files except
   `.env.example` placeholders. Gitleaks must be clean.
5. **Ask before**: changing branch/release strategy, adding a heavy dependency
   or new infrastructure component, moving something between in-scope and
   excluded scope (`DEVELOPMENT_PLAN.md` §3), or starting a later phase before
   the current phase's exit criteria are met.

---

## 1. Branch model

| Branch | Purpose | Rules |
|---|---|---|
| `main` | Always stable, releasable | Protected. No direct pushes. Only PRs from `dev`, `release/*`, or `hotfix/*`. Tagged releases (`v0.1.0`, `v0.2.0`, …). |
| `dev` | Integration branch (default) | Latest development code. Only PRs from work branches. Must pass CI. |
| `feature/<short-desc>` | One task / one feature | Branched from `dev`. Merged back into `dev` via PR. |
| `bugfix/<short-desc>` | Non-urgent bug | Same lifecycle as `feature/*`. |
| `infra/<short-desc>` | Terraform, Helm, Argo CD, CI, Docker Compose | Same lifecycle as `feature/*`. |
| `docs/<short-desc>` | Documentation, ADRs, runbooks | Same lifecycle as `feature/*`. |
| `release/vX.Y.Z` | Pre-release stabilization | Branched from `dev` when `dev` is ready. Only final testing and bug fixes. PR → `main`, then tag. |
| `hotfix/vX.Y.Z` | Urgent fix on a release | Branched from **`main`**. PR → `main` **and** `dev`. Tag new patch release. |

Branch names are short, lowercase, hyphenated descriptions and **contain no
numbers** — no issue number, no username: `feature/incident-state-machine`,
not `feature/12-incident-state-machine`. The issue is linked from the PR
(`Closes #<n>`), not from the branch name.

### 1.1 Repository bootstrap (one time only)

A brand-new repository has no `dev` to branch from, so the very first commit
(plan, workflow, README, `.gitignore`) goes directly on `main`. Immediately
after: create `dev` from `main`, push both, set `dev` as the default branch,
and enable branch protection (§7). From then on §0.1 applies without
exception.

### 1.2 Releases map to plan phases

Tag a minor release when a phase's exit criteria are met, e.g. `v0.1.0` =
Phase 1 complete, `v0.2.0` = Phase 2 complete. `v1.0.0` = the full demo
scenario (`DEVELOPMENT_PLAN.md` §2) works end to end.

---

## 2. The loop, every single task

1. **Open a GitHub issue** describing the task, using the plan's Step 1
   "Define" fields (`DEVELOPMENT_PLAN.md` §9): user story, acceptance
   criteria, failure cases, security risks, observability needs. Assign it
   to its phase milestone. One issue = one unit of work.
2. `git checkout dev && git pull origin dev` — always start from the latest
   `dev`.
3. `git checkout -b feature/<short-desc>`.
4. **Design before code** (plan §9 Step 2): API contract, DB/migration
   changes, event schema, authorization, test plan, rollback.
5. **Test first → implement smallest version → commit** in small,
   single-purpose commits. Never bulk-commit a whole feature at the end.
6. Run the full local gate before pushing (§5). It must be green.
7. Run the **iterative test loop** (§6) for anything touching a UI, API, or
   agent surface. It must be green, warnings included.
8. `git push -u origin feature/<short-desc>`.
9. **Open a PR into `dev`** using the template in §4. Link the issue with
   `Closes #<n>`.
10. **Self-review the PR diff in full** on GitHub and wait for CI to pass.
    Both are required.
11. Squash-or-merge into `dev` (keep history readable). Delete the branch.
12. When a phase's exit criteria are met → `release/vX.Y.Z` → full system
    test (plan §23, as far as built) → PR to `main` → merge → tag.
13. For urgent fixes on a release → `hotfix/vX.Y.Z` from `main` → fix → PR to
    `main` **and** back-merge to `dev` → tag patch release.

---

## 3. Commits and authorship

### 3.1 Authorship — hard rule

Every commit is authored **only** by `Kunj157 <kunjr157@gmail.com>`.
Concretely:

- Commit with the repository's configured identity. Do **not** pass
  `--author`, do **not** set `GIT_AUTHOR_*` / `GIT_COMMITTER_*` overrides,
  and do **not** add any trailer naming a tool or assistant.
- **Forbidden strings** anywhere in a commit message, PR title, or PR body:
  `Co-Authored-By:`, `Co-authored-by:`, `Generated with`, `Claude`,
  `Cursor`, `Copilot`, `ChatGPT`, `🤖`.
  (Filenames such as `CLAUDE.md` may exist in the tree; they just never get
  named in a commit message — say "agent instructions" instead.)
- If a commit template or tool tries to append attribution, strip it before
  committing. Verify after every commit:
  ```
  git log -1 --format='%an <%ae>%n%b'
  ```
  The author line must read `Kunj157 <kunjr157@gmail.com>` and the body must
  contain no co-author trailer.

### 3.2 Message format — Conventional Commits

```
<type>(<scope>): <subject>

<body>

<footer>
```

- **Types:** `feat`, `fix`, `docs`, `style`, `refactor`, `test`, `chore`,
  `ci`, `build`, `perf`.
- **Scopes:** `web`, `api`, `worker`, `ml`, `agent`, `demo`, `infra`,
  `helm`, `observability`, `ci`, `docs`, `deps`.
- **Subject:** imperative, lowercase, no trailing period, ≤ 72 chars.
- **Body:** what changed **and why**. Wrap at 72 columns. Not optional for
  anything non-trivial.
- **Footer:** `Closes #12`, `Refs #9`, `BREAKING CHANGE: …`.

Examples:

```
feat(api): add incident state transition service

All status changes must go through one domain service so every
transition writes an incident event and an audit record. Invalid
transitions return 409; stale versions are rejected via optimistic
locking.

Closes #14
```

```
fix(worker): prevent duplicate remediation execution
```

One logical change per commit. If the subject needs an "and", split it.

---

## 4. Self-review (replaces team code review)

There is no second reviewer, so the discipline has to come from the process.

- **Small PRs.** One issue = one PR. If the diff exceeds ~400 changed lines
  (excluding lockfiles and generated code), split it.
- **Link the issue.** Every PR closes or references one.
- **Read the entire diff on GitHub** before merging — not in the editor.
- **PR description template** (from `DEVELOPMENT_PLAN.md` §8.2):
  ```
  ## Summary
  ## Reason for change
  ## How it was tested        (commands run, flows driven, results)
  ## Screenshots              (UI changes)
  ## Security implications
  ## Migration notes          (Alembic revision, env vars, breaking changes)
  ## Rollback procedure
  ## Definition of done       (checklist below)
  Closes #<n>
  ```
- **Self-review checklist, every PR:**
  - [ ] No debug prints, `console.log`, commented-out code, or `TODO` without
        an issue number.
  - [ ] No secrets, tokens, cloud account IDs, or absolute local paths.
  - [ ] Tests added/updated first, and passing, for the new behavior.
  - [ ] Authorization tested for every new/changed endpoint (401/403/
        cross-org).
  - [ ] Mutations write audit records; logs and metrics emitted.
  - [ ] UI flows covered by a committed Playwright spec or Vitest test, green
        headless (§6).
  - [ ] No browser console errors, React warnings, or hydration warnings.
  - [ ] Agent changes: schema-valid output, tool allow-list enforced, eval
        cases added (`tests/agent-evals/`).
  - [ ] Alembic migration added and reversible, if the schema changed.
  - [ ] Docs / README / ADR updated if behavior or setup changed.
  - [ ] No dead code, no duplication introduced.
  - [ ] Commit messages follow §3, no AI co-author trailers.
- **Never merge red CI.** Never merge with "will fix in the next PR".

---

## 5. Local gate before every push

Run from the repo root, in this order; all must pass. The `make` targets are
defined in the root `Makefile` (plan §10.4); until a target exists, run the
underlying command directly and add the target in the same PR.

1. **Format** — `make format` (ruff format, prettier) → no diff left behind.
2. **Lint** — `make lint` (ruff, eslint) → zero warnings on changed code.
3. **Type check** — `make typecheck` (mypy strict for Python, `tsc --noEmit`
   for TypeScript).
4. **Unit tests** — `make test` (pytest, Vitest).
5. **Integration tests** — `make test-integration` (pytest + Testcontainers
   for PostgreSQL/Redis/Redpanda). Docker must be running; integration tests
   must **fail**, not silently skip, when their dependencies are missing.
6. **E2E** — `make test-e2e` (Playwright, headless) for anything touching
   the web app.
7. **Agent evals** — `make test-agent` for anything touching agents,
   prompts, tools, or retrieval.
8. **Build** — `make build` (Next.js build, Python packages, Docker images
   for changed apps).
9. **Secret scan** — `gitleaks detect --no-banner` clean.

CI (`.github/workflows/pull-request.yml`) enforces the same gate plus
Semgrep, dependency audit, Trivy, Terraform validate, and Helm lint (plan
§20.1). Local-first is not optional: CI is the backstop, not the first run.

---

## 6. Testing — driven, iterative, headless

### 6.1 Pick the right driver

| Surface | Driver |
|---|---|
| Domain logic (state machine, policies, detectors, risk) | pytest unit tests, no I/O |
| FastAPI endpoints | pytest + `httpx.AsyncClient` against the app; Testcontainers for DB/Redis |
| DB migrations / repositories | pytest + Testcontainers PostgreSQL (with pgvector) |
| Workers, queues, events | pytest + Testcontainers Redis/Redpanda; assert idempotency and retries |
| React components | Vitest + Testing Library |
| Browser flows (`apps/web`) | **Playwright MCP server** while iterating → committed Playwright spec in `tests/e2e/` |
| 3D topology | Playwright: selection, keyboard, reduced-motion, WebGL-failure → 2D fallback |
| Agents / RAG | Fixed eval dataset in `tests/agent-evals/` (tool sequence, runbook hit, groundedness, forbidden actions); LLM mocked for unit tests |
| ML | pytest on feature schema, determinism, no future leakage; evaluation report in `ml/evaluation/` |
| Performance / chaos | k6 in `tests/performance/`, Chaos Mesh scenarios in `tests/chaos/` |
| Infrastructure | `terraform validate`, tflint, Checkov, `helm lint` |

### 6.2 Design for testability first

Most bugs should be catchable without a browser or an LLM. Keep logic in
plain Python domain services and pure TypeScript functions/hooks; keep route
handlers, React components, and agent nodes thin. Tools are normal functions
tested before they are wired to a model (plan Phase 8 Step 2). Then the bulk
of coverage is fast unit tests, and Playwright/agent evals only cover genuine
interaction and reasoning behavior.

### 6.3 The iterative loop

Do not stop at "it built" or "the page loaded". Loop until the behavior is
right:

1. **Write the failing test first** for the next smallest behavior (red →
   green → refactor).
2. **Run it headless** — `make test` / `make test-integration` /
   `pnpm --filter web exec playwright test`.
3. **Drive the real user flow** — for web surfaces, use the Playwright MCP
   server: navigate, snapshot the accessibility tree, click, type, submit,
   navigate. Not just the happy path: also the empty state, invalid input,
   unauthorized role, and dependency-down / SSE-disconnect path.
4. **Assert on observable behavior** — HTTP status and body, DB rows, audit
   records, emitted events, rendered accessible text — not on internal
   implementation details. Use Playwright auto-waiting / `expect.poll`
   instead of sleeps.
5. **Watch the output** — browser console, network tab, server logs. A test
   that passes while emitting React warnings, unhandled promise rejections,
   or 5xx responses is not green.
6. **Look at it** for anything visual — screenshot at 1440 / 1024 / 768 /
   390 px (plan §16.5). If it diverges from intent → fix → back to step 2.
7. Once a flow is verified via MCP, **commit it as a Playwright spec** so CI
   protects it.
8. **Record the outcome** in the PR description: flows exercised,
   screenshots for visual changes, and anything deliberately left untested.

Report the loop honestly. If a step failed or was skipped, say so — never
describe an untested change as verified.

### 6.4 What must exist before a PR merges

- **Unit tests** for every new behavior, written before the implementation.
- **Authorization tests** for every new or changed endpoint.
- **Integration tests** for critical cross-component flows (API → DB → SSE,
  detector → incident, approval → execution → verification).
- **Playwright specs** for every new or changed UI flow, committed to
  `tests/e2e/`.
- **Agent eval cases** for every new agent, tool, or prompt version.
- **Visual snapshots** only for key screens where layout regressions matter —
  keep them few.
- All of it wired into `make` targets so CI runs it headless on every PR.
- Coverage of domain and security-critical code must not drop.

---

## 7. Branch protection (configure once on GitHub)

- Protect `main` and `dev`.
- Require status checks to pass before merging.
- Require branches to be up to date before merging.
- Restrict direct pushes; changes land only via PR.
- Solo exception: required approvals = `0`, since you cannot approve your
  own PR — the §4 self-review checklist substitutes for it. Everything else
  stays on.

---

## 8. Project structure

Follow `DEVELOPMENT_PLAN.md` §7 exactly. Do not create top-level directories
that are not listed there without asking (§0.5). `docs/` is committed — the
architecture, ADRs, runbooks, and threat model are deliverables.

---

## 9. General practices

- Pull the latest `dev` before starting any work.
- Track everything in GitHub Issues — a task without an issue does not exist.
- One GitHub milestone per plan phase; a GitHub Projects board shows what is
  in flight. As a solo dev, keep **at most one** item in "In Progress".
- Work the plan in order (§34 starting checklist, §35 core rule). Do not
  start excluded-scope work (§3.2).
- Update docs, README, and ADRs in the same PR as the behavior change.
- Keep dependencies current (Dependabot/Renovate); review their PRs like any
  other.
- Tag every release. Write release notes from the merged PR titles.
- Clean code, clear commits, honest status reports. Resume metrics come only
  from real measurements.

---

## 10. Agent conduct in this repo

Any coding agent working in this repository:

- Reads `DEVELOPMENT_PLAN.md` and this file before starting.
- Follows this workflow end to end without being reminded.
- Never commits or pushes unless explicitly asked; and when asked, obeys
  §3.1 authorship rules exactly and verifies with `git log -1`.
- Never opens a PR to `main` from a work branch.
- Never claims a change is tested unless it ran the §6 loop; if a step was
  skipped, says which one and why.
- Surfaces a rule conflict instead of silently working around it.
