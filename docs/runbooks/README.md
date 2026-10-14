# Runbooks

Operational runbooks for the demo shop. OpsPilot ingests them (`make
seed-runbooks`) so agents and responders can retrieve the right procedure for
an incident, with citations.

Every runbook has front matter (`title`, `services`, `owner`, `version`, and
optionally `environment`) and
the sections Scope, Symptoms, Prerequisites, Investigation steps, Safe actions,
High-risk actions, Verification, Rollback, and Escalation. Runbook text is
guidance for people and agents; it never grants permissions. Remediation is
limited by OpsPilot's policy, whatever a runbook says.

## Retrieval filters

Search (`GET /api/v1/runbooks/search`, and the agents' `search_runbooks` tool)
narrows results before ranking:

- `service` keeps runbooks that list that service, plus generic runbooks that
  list no services. Service-specific runbooks rank slightly higher.
- `environment` keeps runbooks whose front matter `environment` names that
  environment, plus runbooks for `all` (the default when it is omitted). The
  worker searches with its own `APP_ENV`.
