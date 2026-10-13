# Architecture Decision Records

One file per decision: `NNN-short-title.md`. ADRs are immutable once
accepted — to change a decision, write a new ADR that supersedes the old one
and update the old one's status line.

| ADR | Title | Status |
|---|---|---|
| [001](001-technology-stack.md) | Technology stack | Accepted |
| [002](002-modular-monolith.md) | Modular monolith over microservices | Accepted |
| [003](003-human-approved-remediation.md) | Human-approved, allow-listed remediation | Accepted |

## Template

```markdown
# ADR-NNN: Title

- Status: Proposed | Accepted | Superseded by ADR-XXX
- Date: YYYY-MM-DD

## Context
## Decision
## Consequences
## Alternatives considered
```
