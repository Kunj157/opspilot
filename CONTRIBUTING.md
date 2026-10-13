# Contributing to OpsPilot

OpsPilot is a solo project. This file is the short version of the rules;
[`DEVELOPMENT_WORKFLOW.md`](DEVELOPMENT_WORKFLOW.md) is the full, binding
version and wins on any conflict.

## Before you start

1. Read [`DEVELOPMENT_PLAN.md`](DEVELOPMENT_PLAN.md) — it defines scope,
   order of work, and the definition of done.
2. Make sure an issue exists for the work. A task without an issue does not
   exist.

## Making a change

```bash
git checkout dev && git pull origin dev
git checkout -b feature/<short-desc>     # or bugfix/ infra/ docs/
# test first → smallest implementation → small commits
make format lint typecheck test test-integration build
git push -u origin feature/<short-desc>
```

Then open a pull request **into `dev`** and fill in every section of the
template.

## Commits

[Conventional Commits](https://www.conventionalcommits.org/):

```
feat(api): add incident creation endpoint

Body explaining what and why, wrapped at 72 columns.

Closes #12
```

Types: `feat`, `fix`, `docs`, `style`, `refactor`, `test`, `chore`, `ci`,
`build`, `perf`. One logical change per commit. No co-author trailers or
tool attribution.

## Merging

- CI must be green. Never merge red.
- Read the full diff on GitHub before merging.
- PRs over ~400 changed lines (excluding lockfiles) get split.

## Releases

A release branch is cut from `dev` when a plan phase meets its exit
criteria, merged into `main`, and tagged (`v0.<phase>.0`).

## Security

Never commit secrets — only placeholder values in `.env.example`. Report a
vulnerability privately via GitHub security advisories rather than a public
issue.
