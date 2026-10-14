# Runbooks

Operational runbooks for the demo shop. OpsPilot ingests them (`make
seed-runbooks`) so agents and responders can retrieve the right procedure for
an incident, with citations.

Every runbook has front matter (`title`, `services`, `owner`, `version`) and
the sections Scope, Symptoms, Prerequisites, Investigation steps, Safe actions,
High-risk actions, Verification, Rollback, and Escalation. Runbook text is
guidance for people and agents; it never grants permissions. Remediation is
limited by OpsPilot's policy, whatever a runbook says.
