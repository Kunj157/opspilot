## Summary

<!-- What changed, in one or two sentences. -->

## Reason for change

## How it was tested

<!-- Commands run, flows driven (Playwright MCP / specs), results. -->

## Screenshots

<!-- UI changes only: 1440 / 1024 / 768 / 390 px. -->

## Security implications

## Migration notes

<!-- Alembic revision, new env vars, breaking changes. "None" if none. -->

## Rollback procedure

## Definition of done

- [ ] Acceptance criteria from the linked issue are met
- [ ] Tests written first and passing (unit / integration / e2e / agent evals as applicable)
- [ ] Authorization tested for new or changed endpoints
- [ ] Sensitive actions write audit records; logs and metrics emitted
- [ ] No console errors, React warnings, or 5xx responses in the test run
- [ ] Local gate green (`make format lint typecheck test test-integration build`)
- [ ] Docs / README / ADRs updated
- [ ] No secrets, debug output, or untracked TODOs
- [ ] Commits follow Conventional Commits, no co-author trailers
- [ ] Full diff self-reviewed on GitHub

Closes #
