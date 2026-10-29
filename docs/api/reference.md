# OpsPilot API reference

Generated from the OpenAPI schema by `make api-docs`; do not edit by hand. The machine-readable schema is [`packages/api-client/openapi.json`](../../packages/api-client/openapi.json), and a running API serves it at `/openapi.json` with interactive docs at `/docs`.

## Conventions

- Every route lives under `/api/v1`. Send `Authorization: Bearer <access token>` on everything except the health checks. `scripts/dev-token.sh` prints a token for the local Keycloak realm.
- Roles are enforced per route by a permission dependency; a missing token is 401 and an insufficient role is 403. Resources of another organization return 404.
- Every mutation accepts an `Idempotency-Key` header; a replay returns the stored response.
- Rate limits return 429 with `Retry-After`. Validation errors return 422.

## Endpoints

| Tag | Operations |
|---|---|
| [audit](#audit) | 1 |
| [evaluations](#evaluations) | 1 |
| [health](#health) | 2 |
| [identity](#identity) | 1 |
| [incidents](#incidents) | 12 |
| [investigations](#investigations) | 7 |
| [ml](#ml) | 4 |
| [remediation](#remediation) | 3 |
| [runbooks](#runbooks) | 7 |
| [services](#services) | 6 |
| [topology](#topology) | 1 |
| [users](#users) | 2 |

### audit

#### `GET /api/v1/audit-logs`

List Audit Logs.

Auth: bearer token

| Parameter | In | Type | Required | Description |
|---|---|---|---|---|
| `action` | query | string or null | no |  |
| `actor_id` | query | string or null | no |  |
| `resource_type` | query | string or null | no |  |
| `since` | query | string (date-time) or null | no |  |
| `until` | query | string (date-time) or null | no |  |
| `limit` | query | integer | no |  |
| `cursor` | query | string or null | no |  |

| Status | Description | Body |
|---|---|---|
| 200 | Successful Response | [AuditLogPage](#auditlogpage) |
| 422 | Validation Error | [HTTPValidationError](#httpvalidationerror) |

### evaluations

#### `GET /api/v1/evaluations`

Evaluations.

Auth: bearer token

| Parameter | In | Type | Required | Description |
|---|---|---|---|---|
| `from` | query | string (date-time) or null | no | Range start; default 30 days ago |
| `to` | query | string (date-time) or null | no | Range end; default now |

| Status | Description | Body |
|---|---|---|
| 200 | Successful Response | [Evaluations](#evaluations) |
| 422 | Validation Error | [HTTPValidationError](#httpvalidationerror) |

### health

#### `GET /api/v1/health`

Health.

Auth: none

| Status | Description | Body |
|---|---|---|
| 200 | Successful Response | [HealthResponse](#healthresponse) |

#### `GET /api/v1/ready`

Ready.

Auth: none

| Status | Description | Body |
|---|---|---|
| 200 | Successful Response | [ReadinessResponse](#readinessresponse) |
| 503 | Service Unavailable | [ReadinessResponse](#readinessresponse) |

### identity

#### `GET /api/v1/me`

Me.

Auth: bearer token

| Status | Description | Body |
|---|---|---|
| 200 | Successful Response | [MeResponse](#meresponse) |

### incidents

#### `GET /api/v1/incidents/stream`

Stream Organization Incidents.

Auth: bearer token

| Parameter | In | Type | Required | Description |
|---|---|---|---|---|
| `Last-Event-ID` | header | string or null | no |  |

| Status | Description | Body |
|---|---|---|
| 200 | Successful Response |  |
| 422 | Validation Error | [HTTPValidationError](#httpvalidationerror) |

#### `GET /api/v1/incidents/{incident_id}/stream`

Stream Incident.

Auth: bearer token

| Parameter | In | Type | Required | Description |
|---|---|---|---|---|
| `incident_id` | path | string (uuid) | yes |  |
| `Last-Event-ID` | header | string or null | no |  |

| Status | Description | Body |
|---|---|---|
| 200 | Successful Response |  |
| 422 | Validation Error | [HTTPValidationError](#httpvalidationerror) |

#### `GET /api/v1/incidents`

List Incidents.

Auth: bearer token

| Parameter | In | Type | Required | Description |
|---|---|---|---|---|
| `status` | query | array of [IncidentStatus](#incidentstatus) or null | no |  |
| `severity` | query | array of [Severity](#severity) or null | no |  |
| `service_id` | query | string (uuid) or null | no |  |
| `assigned_user_id` | query | string (uuid) or null | no |  |
| `source` | query | `manual` / `detector` / `alertmanager` or null | no |  |
| `since` | query | string (date-time) or null | no |  |
| `until` | query | string (date-time) or null | no |  |
| `limit` | query | integer | no |  |
| `cursor` | query | string or null | no |  |

| Status | Description | Body |
|---|---|---|
| 200 | Successful Response | [IncidentPage](#incidentpage) |
| 422 | Validation Error | [HTTPValidationError](#httpvalidationerror) |

#### `POST /api/v1/incidents`

Create Incident.

Auth: bearer token

| Parameter | In | Type | Required | Description |
|---|---|---|---|---|
| `Idempotency-Key` | header | string or null | no |  |

Request body: [IncidentCreate](#incidentcreate)

| Status | Description | Body |
|---|---|---|
| 201 | Successful Response | [IncidentOut](#incidentout) |
| 422 | Validation Error | [HTTPValidationError](#httpvalidationerror) |

#### `GET /api/v1/incidents/{incident_id}`

Get Incident.

Auth: bearer token

| Parameter | In | Type | Required | Description |
|---|---|---|---|---|
| `incident_id` | path | string (uuid) | yes |  |

| Status | Description | Body |
|---|---|---|
| 200 | Successful Response | [IncidentOut](#incidentout) |
| 422 | Validation Error | [HTTPValidationError](#httpvalidationerror) |

#### `PATCH /api/v1/incidents/{incident_id}`

Update Incident.

Auth: bearer token

| Parameter | In | Type | Required | Description |
|---|---|---|---|---|
| `incident_id` | path | string (uuid) | yes |  |
| `Idempotency-Key` | header | string or null | no |  |

Request body: [IncidentUpdate](#incidentupdate)

| Status | Description | Body |
|---|---|---|
| 200 | Successful Response | [IncidentOut](#incidentout) |
| 422 | Validation Error | [HTTPValidationError](#httpvalidationerror) |

#### `POST /api/v1/incidents/{incident_id}/acknowledge`

Acknowledge Incident.

Auth: bearer token

| Parameter | In | Type | Required | Description |
|---|---|---|---|---|
| `incident_id` | path | string (uuid) | yes |  |
| `Idempotency-Key` | header | string or null | no |  |

Request body: [VersionedRequest](#versionedrequest)

| Status | Description | Body |
|---|---|---|
| 200 | Successful Response | [IncidentOut](#incidentout) |
| 422 | Validation Error | [HTTPValidationError](#httpvalidationerror) |

#### `POST /api/v1/incidents/{incident_id}/investigate`

Investigate Incident.

Auth: bearer token

| Parameter | In | Type | Required | Description |
|---|---|---|---|---|
| `incident_id` | path | string (uuid) | yes |  |
| `Idempotency-Key` | header | string or null | no |  |

Request body: [VersionedRequest](#versionedrequest)

| Status | Description | Body |
|---|---|---|
| 200 | Successful Response | [IncidentOut](#incidentout) |
| 422 | Validation Error | [HTTPValidationError](#httpvalidationerror) |

#### `POST /api/v1/incidents/{incident_id}/resolve`

Resolve Incident.

Auth: bearer token

| Parameter | In | Type | Required | Description |
|---|---|---|---|---|
| `incident_id` | path | string (uuid) | yes |  |
| `Idempotency-Key` | header | string or null | no |  |

Request body: [VersionedRequest](#versionedrequest)

| Status | Description | Body |
|---|---|---|
| 200 | Successful Response | [IncidentOut](#incidentout) |
| 422 | Validation Error | [HTTPValidationError](#httpvalidationerror) |

#### `GET /api/v1/incidents/{incident_id}/events`

List Incident Events.

Auth: bearer token

| Parameter | In | Type | Required | Description |
|---|---|---|---|---|
| `incident_id` | path | string (uuid) | yes |  |

| Status | Description | Body |
|---|---|---|
| 200 | Successful Response | [EventList](#eventlist) |
| 422 | Validation Error | [HTTPValidationError](#httpvalidationerror) |

#### `GET /api/v1/incident-metrics`

Incident Metrics.

Auth: bearer token

| Parameter | In | Type | Required | Description |
|---|---|---|---|---|
| `days` | query | integer | no |  |

| Status | Description | Body |
|---|---|---|
| 200 | Successful Response | [IncidentMetrics](#incidentmetrics) |
| 422 | Validation Error | [HTTPValidationError](#httpvalidationerror) |

#### `GET /api/v1/incidents/{incident_id}/detections`

List Detections.

Auth: bearer token

| Parameter | In | Type | Required | Description |
|---|---|---|---|---|
| `incident_id` | path | string (uuid) | yes |  |

| Status | Description | Body |
|---|---|---|
| 200 | Successful Response | [DetectionList](#detectionlist) |
| 422 | Validation Error | [HTTPValidationError](#httpvalidationerror) |

### investigations

#### `GET /api/v1/incidents/{incident_id}/investigation`

Latest Investigation.

Auth: bearer token

| Parameter | In | Type | Required | Description |
|---|---|---|---|---|
| `incident_id` | path | string (uuid) | yes |  |

| Status | Description | Body |
|---|---|---|
| 200 | Successful Response | [InvestigationOut](#investigationout) |
| 422 | Validation Error | [HTTPValidationError](#httpvalidationerror) |

#### `POST /api/v1/incidents/{incident_id}/investigation`

Start Investigation.

Queue an agent investigation; returns the running one if there already is one.

Auth: bearer token

| Parameter | In | Type | Required | Description |
|---|---|---|---|---|
| `incident_id` | path | string (uuid) | yes |  |
| `Idempotency-Key` | header | string or null | no |  |

| Status | Description | Body |
|---|---|---|
| 202 | Successful Response | [InvestigationOut](#investigationout) |
| 200 | Already investigating | [InvestigationOut](#investigationout) |
| 422 | Validation Error | [HTTPValidationError](#httpvalidationerror) |

#### `GET /api/v1/incidents/{incident_id}/evidence`

List Evidence.

Auth: bearer token

| Parameter | In | Type | Required | Description |
|---|---|---|---|---|
| `incident_id` | path | string (uuid) | yes |  |

| Status | Description | Body |
|---|---|---|
| 200 | Successful Response | [Items_EvidenceOut_](#items_evidenceout_) |
| 422 | Validation Error | [HTTPValidationError](#httpvalidationerror) |

#### `GET /api/v1/incidents/{incident_id}/agent-runs`

List Agent Runs.

Auth: bearer token

| Parameter | In | Type | Required | Description |
|---|---|---|---|---|
| `incident_id` | path | string (uuid) | yes |  |

| Status | Description | Body |
|---|---|---|
| 200 | Successful Response | [Items_AgentRunOut_](#items_agentrunout_) |
| 422 | Validation Error | [HTTPValidationError](#httpvalidationerror) |

#### `GET /api/v1/incidents/{incident_id}/proposals`

List Proposals.

Auth: bearer token

| Parameter | In | Type | Required | Description |
|---|---|---|---|---|
| `incident_id` | path | string (uuid) | yes |  |

| Status | Description | Body |
|---|---|---|
| 200 | Successful Response | [Items_ProposalOut_](#items_proposalout_) |
| 422 | Validation Error | [HTTPValidationError](#httpvalidationerror) |

#### `GET /api/v1/incidents/{incident_id}/postmortem`

Get Postmortem.

Auth: bearer token

| Parameter | In | Type | Required | Description |
|---|---|---|---|---|
| `incident_id` | path | string (uuid) | yes |  |

| Status | Description | Body |
|---|---|---|
| 200 | Successful Response | [PostmortemOut](#postmortemout) |
| 422 | Validation Error | [HTTPValidationError](#httpvalidationerror) |

#### `POST /api/v1/incidents/{incident_id}/postmortem`

Request Postmortem.

Ask the worker to (re)draft the postmortem of a resolved incident.

Auth: bearer token

| Parameter | In | Type | Required | Description |
|---|---|---|---|---|
| `incident_id` | path | string (uuid) | yes |  |
| `Idempotency-Key` | header | string or null | no |  |

| Status | Description | Body |
|---|---|---|
| 202 | Successful Response | [PostmortemOut](#postmortemout) |
| 422 | Validation Error | [HTTPValidationError](#httpvalidationerror) |

### ml

#### `GET /api/v1/ml/models`

List Models.

Auth: bearer token

| Status | Description | Body |
|---|---|---|
| 200 | Successful Response | [ModelList](#modellist) |

#### `POST /api/v1/ml/models/{model_id}/promote`

Promote Model.

Run this version in shadow mode; promoting an older version is the rollback.

Auth: bearer token

| Parameter | In | Type | Required | Description |
|---|---|---|---|---|
| `model_id` | path | string (uuid) | yes |  |
| `Idempotency-Key` | header | string or null | no |  |

| Status | Description | Body |
|---|---|---|
| 200 | Successful Response | [ModelOut](#modelout) |
| 422 | Validation Error | [HTTPValidationError](#httpvalidationerror) |

#### `POST /api/v1/ml/score`

Score Windows.

Score posted windows with the shadow model (history first, newest last).

Auth: bearer token

Request body: [ScoreIn](#scorein)

| Status | Description | Body |
|---|---|---|
| 200 | Successful Response | [ScoreOut](#scoreout) |
| 422 | Validation Error | [HTTPValidationError](#httpvalidationerror) |

#### `GET /api/v1/ml/shadow`

Shadow Summary.

Per service: shadow predictions and alerts next to the rule's triggers and incidents.

Auth: bearer token

| Parameter | In | Type | Required | Description |
|---|---|---|---|---|
| `hours` | query | integer | no |  |

| Status | Description | Body |
|---|---|---|
| 200 | Successful Response | [ShadowSummary](#shadowsummary) |
| 422 | Validation Error | [HTTPValidationError](#httpvalidationerror) |

### remediation

#### `GET /api/v1/proposals/{proposal_id}`

Get Proposal.

Auth: bearer token

| Parameter | In | Type | Required | Description |
|---|---|---|---|---|
| `proposal_id` | path | string (uuid) | yes |  |

| Status | Description | Body |
|---|---|---|
| 200 | Successful Response | [ProposalOut](#proposalout) |
| 422 | Validation Error | [HTTPValidationError](#httpvalidationerror) |

#### `POST /api/v1/proposals/{proposal_id}/approve`

Approve Proposal.

Approve the reviewed version; the worker then executes it once.

Auth: bearer token

| Parameter | In | Type | Required | Description |
|---|---|---|---|---|
| `proposal_id` | path | string (uuid) | yes |  |
| `Idempotency-Key` | header | string or null | no |  |

Request body: [DecisionIn](#decisionin)

| Status | Description | Body |
|---|---|---|
| 200 | Successful Response | [ProposalOut](#proposalout) |
| 422 | Validation Error | [HTTPValidationError](#httpvalidationerror) |

#### `POST /api/v1/proposals/{proposal_id}/reject`

Reject Proposal.

Auth: bearer token

| Parameter | In | Type | Required | Description |
|---|---|---|---|---|
| `proposal_id` | path | string (uuid) | yes |  |
| `Idempotency-Key` | header | string or null | no |  |

Request body: [DecisionIn](#decisionin)

| Status | Description | Body |
|---|---|---|
| 200 | Successful Response | [ProposalOut](#proposalout) |
| 422 | Validation Error | [HTTPValidationError](#httpvalidationerror) |

### runbooks

#### `GET /api/v1/runbooks`

List Runbooks.

Auth: bearer token

| Parameter | In | Type | Required | Description |
|---|---|---|---|---|
| `status` | query | `active` / `archived` / `all` | no |  |

| Status | Description | Body |
|---|---|---|
| 200 | Successful Response | [RunbookList](#runbooklist) |
| 422 | Validation Error | [HTTPValidationError](#httpvalidationerror) |

#### `POST /api/v1/runbooks`

Create Runbook.

Auth: bearer token

| Parameter | In | Type | Required | Description |
|---|---|---|---|---|
| `Idempotency-Key` | header | string or null | no |  |

Request body: [RunbookCreate](#runbookcreate)

| Status | Description | Body |
|---|---|---|
| 201 | Successful Response | [RunbookOut](#runbookout) |
| 422 | Validation Error | [HTTPValidationError](#httpvalidationerror) |

#### `GET /api/v1/runbooks/search`

Search Runbooks.

Runbooks for the service (or generic) and the environment (or all), best first.

Auth: bearer token

| Parameter | In | Type | Required | Description |
|---|---|---|---|---|
| `q` | query | string | yes |  |
| `service` | query | string or null | no |  |
| `environment` | query | string or null | no |  |
| `limit` | query | integer | no |  |

| Status | Description | Body |
|---|---|---|
| 200 | Successful Response | [RunbookHits](#runbookhits) |
| 422 | Validation Error | [HTTPValidationError](#httpvalidationerror) |

#### `POST /api/v1/runbooks/reindex`

Reindex Runbooks.

Re-embed every active runbook, e.g. after changing the embedding model.

Auth: bearer token

| Parameter | In | Type | Required | Description |
|---|---|---|---|---|
| `Idempotency-Key` | header | string or null | no |  |

| Status | Description | Body |
|---|---|---|
| 200 | Successful Response | [ReindexResult](#reindexresult) |
| 422 | Validation Error | [HTTPValidationError](#httpvalidationerror) |

#### `GET /api/v1/runbooks/{runbook_id}`

Get Runbook.

Auth: bearer token

| Parameter | In | Type | Required | Description |
|---|---|---|---|---|
| `runbook_id` | path | string (uuid) | yes |  |

| Status | Description | Body |
|---|---|---|
| 200 | Successful Response | [RunbookOut](#runbookout) |
| 422 | Validation Error | [HTTPValidationError](#httpvalidationerror) |

#### `PUT /api/v1/runbooks/{runbook_id}`

Update Runbook.

Replace the content; a change creates the next version, an identical text changes nothing.

Auth: bearer token

| Parameter | In | Type | Required | Description |
|---|---|---|---|---|
| `runbook_id` | path | string (uuid) | yes |  |
| `Idempotency-Key` | header | string or null | no |  |

Request body: [RunbookWrite](#runbookwrite)

| Status | Description | Body |
|---|---|---|
| 200 | Successful Response | [RunbookOut](#runbookout) |
| 422 | Validation Error | [HTTPValidationError](#httpvalidationerror) |

#### `POST /api/v1/runbooks/{runbook_id}/archive`

Archive Runbook.

Auth: bearer token

| Parameter | In | Type | Required | Description |
|---|---|---|---|---|
| `runbook_id` | path | string (uuid) | yes |  |
| `Idempotency-Key` | header | string or null | no |  |

| Status | Description | Body |
|---|---|---|
| 200 | Successful Response | [RunbookOut](#runbookout) |
| 422 | Validation Error | [HTTPValidationError](#httpvalidationerror) |

### services

#### `GET /api/v1/services`

List Services.

Auth: bearer token

| Status | Description | Body |
|---|---|---|
| 200 | Successful Response | [ServiceList](#servicelist) |

#### `POST /api/v1/services`

Create Service.

Auth: bearer token

| Parameter | In | Type | Required | Description |
|---|---|---|---|---|
| `Idempotency-Key` | header | string or null | no |  |

Request body: [ServiceCreate](#servicecreate)

| Status | Description | Body |
|---|---|---|
| 201 | Successful Response | [ServiceOut](#serviceout) |
| 422 | Validation Error | [HTTPValidationError](#httpvalidationerror) |

#### `GET /api/v1/services/{service_id}`

Get Service.

Auth: bearer token

| Parameter | In | Type | Required | Description |
|---|---|---|---|---|
| `service_id` | path | string (uuid) | yes |  |

| Status | Description | Body |
|---|---|---|
| 200 | Successful Response | [ServiceOut](#serviceout) |
| 422 | Validation Error | [HTTPValidationError](#httpvalidationerror) |

#### `PATCH /api/v1/services/{service_id}`

Update Service.

Auth: bearer token

| Parameter | In | Type | Required | Description |
|---|---|---|---|---|
| `service_id` | path | string (uuid) | yes |  |
| `Idempotency-Key` | header | string or null | no |  |

Request body: [ServiceUpdate](#serviceupdate)

| Status | Description | Body |
|---|---|---|
| 200 | Successful Response | [ServiceOut](#serviceout) |
| 422 | Validation Error | [HTTPValidationError](#httpvalidationerror) |

#### `GET /api/v1/services/{service_id}/dependencies`

List Dependencies.

Services this service calls.

Auth: bearer token

| Parameter | In | Type | Required | Description |
|---|---|---|---|---|
| `service_id` | path | string (uuid) | yes |  |

| Status | Description | Body |
|---|---|---|
| 200 | Successful Response | [ServiceList](#servicelist) |
| 422 | Validation Error | [HTTPValidationError](#httpvalidationerror) |

#### `PUT /api/v1/services/{service_id}/dependencies`

Replace Dependencies.

Replace the full set of services this service calls.

Auth: bearer token

| Parameter | In | Type | Required | Description |
|---|---|---|---|---|
| `service_id` | path | string (uuid) | yes |  |
| `Idempotency-Key` | header | string or null | no |  |

Request body: [DependenciesUpdate](#dependenciesupdate)

| Status | Description | Body |
|---|---|---|
| 200 | Successful Response | [ServiceList](#servicelist) |
| 422 | Validation Error | [HTTPValidationError](#httpvalidationerror) |

### topology

#### `GET /api/v1/topology`

Get Topology.

Auth: bearer token

| Status | Description | Body |
|---|---|---|
| 200 | Successful Response | [Topology](#topology) |

### users

#### `GET /api/v1/users`

List Users.

Users of the caller's organization, newest first. Read-only: roles come from Keycloak.

Auth: bearer token

| Parameter | In | Type | Required | Description |
|---|---|---|---|---|
| `limit` | query | integer | no |  |
| `cursor` | query | string or null | no |  |

| Status | Description | Body |
|---|---|---|
| 200 | Successful Response | [UserPage](#userpage) |
| 422 | Validation Error | [HTTPValidationError](#httpvalidationerror) |

#### `GET /api/v1/users/{user_id}`

Get User.

One user of the caller's organization; another organization's user is 404.

Auth: bearer token

| Parameter | In | Type | Required | Description |
|---|---|---|---|---|
| `user_id` | path | string (uuid) | yes |  |

| Status | Description | Body |
|---|---|---|
| 200 | Successful Response | [UserItem](#useritem) |
| 422 | Validation Error | [HTTPValidationError](#httpvalidationerror) |

## Schemas

### ActorType

One of: `user`, `agent`, `system`

### AgentMetrics

| Field | Type | Required | Description |
|---|---|---|---|
| `runs` | integer | yes | Agent (model) calls started in the range |
| `success_rate` | number or null | yes | Share of agent runs with status succeeded; failed calls and runs that fell back to the fixed plan count against it |
| `tool_calls` | integer | yes | Tool calls made in the range |
| `tool_error_rate` | number or null | yes | Share of tool calls that returned a failed result |
| `input_tokens` | integer | yes | Sum of agent_runs.input_tokens |
| `output_tokens` | integer | yes | Sum of agent_runs.output_tokens |
| `cost_usd` | number | yes | Sum of agent_runs.estimated_cost (USD, estimated) |

### AgentRunOut

| Field | Type | Required | Description |
|---|---|---|---|
| `id` | string (uuid) | yes |  |
| `agent_name` | string | yes |  |
| `status` | string | yes |  |
| `model_provider` | string | yes |  |
| `model_name` | string | yes |  |
| `prompt_version` | string | yes |  |
| `input_tokens` | integer | yes |  |
| `output_tokens` | integer | yes |  |
| `estimated_cost` | number | yes |  |
| `latency_ms` | number | yes |  |
| `error_code` | string or null | yes |  |
| `output` | object or null | yes |  |
| `started_at` | string (date-time) | yes |  |
| `completed_at` | string (date-time) or null | yes |  |
| `tool_calls` | array of [ToolCallOut](#toolcallout) | no |  |

### AuditLogItem

| Field | Type | Required | Description |
|---|---|---|---|
| `id` | string (uuid) | yes |  |
| `actor_type` | [ActorType](#actortype) | yes |  |
| `actor_id` | string | yes |  |
| `action` | string | yes |  |
| `resource_type` | string | yes |  |
| `resource_id` | string or null | yes |  |
| `ip_address` | string or null | yes |  |
| `request_id` | string or null | yes |  |
| `metadata` | object | yes |  |
| `created_at` | string (date-time) | yes |  |

### AuditLogPage

| Field | Type | Required | Description |
|---|---|---|---|
| `items` | array of [AuditLogItem](#auditlogitem) | yes |  |
| `next_cursor` | string or null | yes |  |

### CheckResult

| Field | Type | Required | Description |
|---|---|---|---|
| `status` | `ok` / `fail` | yes |  |
| `detail` | string or null | no |  |

### DailySeverity

| Field | Type | Required | Description |
|---|---|---|---|
| `critical` | integer | no |  |
| `high` | integer | no |  |
| `medium` | integer | no |  |
| `low` | integer | no |  |
| `date` | string (date) | yes |  |

### DecisionIn

| Field | Type | Required | Description |
|---|---|---|---|
| `version` | integer | yes | The proposal version that was reviewed |
| `comment` | string or null | no |  |

### DecisionOut

| Field | Type | Required | Description |
|---|---|---|---|
| `decision` | string | yes |  |
| `proposal_version` | integer | yes |  |
| `reviewed_by` | string (uuid) | yes |  |
| `reviewer_name` | string | yes |  |
| `comment` | string or null | yes |  |
| `reviewed_at` | string (date-time) | yes |  |

### DependenciesUpdate

| Field | Type | Required | Description |
|---|---|---|---|
| `target_ids` | array of string (uuid) | yes |  |

### DetectionList

| Field | Type | Required | Description |
|---|---|---|---|
| `items` | array of [DetectionOut](#detectionout) | yes |  |

### DetectionMetrics

| Field | Type | Required | Description |
|---|---|---|---|
| `incidents` | integer | yes | Detector-opened incidents started in the range |
| `delay_p50_seconds` | number or null | yes | Median seconds from the start of the first anomalous evaluation window linked to an incident (anomaly_detections.window_start) to the incident opening (incidents.started_at): the detection pipeline's own delay |
| `delay_p95_seconds` | number or null | yes | 95th percentile of the same delay |

### DetectionOut

| Field | Type | Required | Description |
|---|---|---|---|
| `id` | string (uuid) | yes |  |
| `service_id` | string (uuid) | yes |  |
| `detector` | string | yes |  |
| `failure_category` | string | yes |  |
| `outcome` | string | yes |  |
| `score` | number or null | yes |  |
| `threshold` | number or null | yes |  |
| `features` | object | yes |  |
| `model_version` | string or null | yes |  |
| `window_start` | string (date-time) | yes |  |
| `window_end` | string (date-time) | yes |  |
| `created_at` | string (date-time) | yes |  |

### Evaluations

| Field | Type | Required | Description |
|---|---|---|---|
| `range_start` | string (date-time) | yes |  |
| `range_end` | string (date-time) | yes |  |
| `detection` | [DetectionMetrics](#detectionmetrics) | yes |  |
| `investigations` | [InvestigationMetrics](#investigationmetrics) | yes |  |
| `agents` | [AgentMetrics](#agentmetrics) | yes |  |
| `remediation` | [RemediationMetrics](#remediationmetrics) | yes |  |
| `response` | [ResponseMetrics](#responsemetrics) | yes |  |

### EventList

| Field | Type | Required | Description |
|---|---|---|---|
| `items` | array of [EventOut](#eventout) | yes |  |

### EventOut

| Field | Type | Required | Description |
|---|---|---|---|
| `id` | string (uuid) | yes |  |
| `sequence` | integer | yes |  |
| `event_type` | string | yes |  |
| `actor_type` | [ActorType](#actortype) | yes |  |
| `actor_id` | string | yes |  |
| `title` | string | yes |  |
| `description` | string or null | yes |  |
| `metadata` | object | yes |  |
| `created_at` | string (date-time) | yes |  |

### EvidenceOut

| Field | Type | Required | Description |
|---|---|---|---|
| `id` | string (uuid) | yes |  |
| `evidence_type` | string | yes |  |
| `source` | string | yes |  |
| `summary` | string | yes |  |
| `content` | object | yes |  |
| `query` | string or null | yes |  |
| `time_range_start` | string (date-time) or null | yes |  |
| `time_range_end` | string (date-time) or null | yes |  |
| `confidence` | number | yes |  |
| `created_at` | string (date-time) | yes |  |

### ExecutionOut

| Field | Type | Required | Description |
|---|---|---|---|
| `id` | string (uuid) | yes |  |
| `status` | [ExecutionStatus](#executionstatus) | yes |  |
| `attempts` | integer | yes |  |
| `started_at` | string (date-time) | yes |  |
| `completed_at` | string (date-time) or null | yes |  |
| `output` | object | yes |  |
| `error_message` | string or null | yes |  |
| `verification_status` | string or null | yes |  |
| `verification` | object | yes |  |
| `verified_at` | string (date-time) or null | yes |  |

### ExecutionStatus

One of: `running`, `succeeded`, `failed`

### HTTPValidationError

| Field | Type | Required | Description |
|---|---|---|---|
| `detail` | array of [ValidationError](#validationerror) | no |  |

### HealthResponse

| Field | Type | Required | Description |
|---|---|---|---|
| `status` | string | yes |  |

### HealthStatus

One of: `unknown`, `healthy`, `degraded`, `critical`

### IncidentCreate

| Field | Type | Required | Description |
|---|---|---|---|
| `title` | string | yes |  |
| `description` | string or null | no |  |
| `severity` | [Severity](#severity) | yes |  |
| `service_id` | string (uuid) or null | no |  |
| `source` | `manual` / `detector` / `alertmanager` | no |  |

### IncidentMetrics

| Field | Type | Required | Description |
|---|---|---|---|
| `window_days` | integer | yes |  |
| `mtta_seconds` | number or null | yes |  |
| `mttr_seconds` | number or null | yes |  |
| `acknowledged` | integer | yes |  |
| `resolved` | integer | yes |  |
| `active_by_severity` | [SeverityCounts](#severitycounts) | yes |  |
| `daily` | array of [DailySeverity](#dailyseverity) | yes |  |

### IncidentOut

| Field | Type | Required | Description |
|---|---|---|---|
| `id` | string (uuid) | yes |  |
| `title` | string | yes |  |
| `description` | string or null | yes |  |
| `severity` | [Severity](#severity) | yes |  |
| `status` | [IncidentStatus](#incidentstatus) | yes |  |
| `source` | string | yes |  |
| `service_id` | string (uuid) or null | yes |  |
| `started_at` | string (date-time) | yes |  |
| `acknowledged_at` | string (date-time) or null | yes |  |
| `resolved_at` | string (date-time) or null | yes |  |
| `detection_score` | number or null | yes |  |
| `assigned_user_id` | string (uuid) or null | yes |  |
| `version` | integer | yes |  |
| `created_at` | string (date-time) | yes |  |
| `updated_at` | string (date-time) | yes |  |
| `allowed_transitions` | array of [IncidentStatus](#incidentstatus) | yes |  |

### IncidentPage

| Field | Type | Required | Description |
|---|---|---|---|
| `items` | array of [IncidentOut](#incidentout) | yes |  |
| `next_cursor` | string or null | yes |  |

### IncidentStatus

Incident lifecycle states; transitions live in incidents.state_machine.

One of: `DETECTED`, `INVESTIGATING`, `AWAITING_APPROVAL`, `REMEDIATING`, `VERIFYING`, `MONITORING`, `RESOLVED`, `REJECTED`

### IncidentUpdate

| Field | Type | Required | Description |
|---|---|---|---|
| `version` | integer | yes |  |
| `title` | string or null | no |  |
| `description` | string or null | no |  |
| `severity` | [Severity](#severity) or null | no |  |
| `service_id` | string (uuid) or null | no |  |
| `assigned_user_id` | string (uuid) or null | no |  |
| `status` | [IncidentStatus](#incidentstatus) or null | no |  |

### InvestigationMetrics

| Field | Type | Required | Description |
|---|---|---|---|
| `total` | integer | yes | Investigations created in the range |
| `succeeded` | integer | yes | Of those, finished with status completed |
| `partial` | integer | yes | Of those, stopped early (limits or model failure) |
| `failed` | integer | yes | Of those, gave up after repeated attempts |

### InvestigationOut

| Field | Type | Required | Description |
|---|---|---|---|
| `id` | string (uuid) | yes |  |
| `incident_id` | string (uuid) | yes |  |
| `status` | [InvestigationStatus](#investigationstatus) | yes |  |
| `current_node` | string or null | yes |  |
| `round` | integer | yes |  |
| `result` | object or null | yes |  |
| `error` | string or null | yes |  |
| `tool_calls` | integer | yes |  |
| `input_tokens` | integer | yes |  |
| `output_tokens` | integer | yes |  |
| `cost_usd` | number | yes |  |
| `created_at` | string (date-time) | yes |  |
| `started_at` | string (date-time) or null | yes |  |
| `completed_at` | string (date-time) or null | yes |  |

### InvestigationStatus

One of: `queued`, `running`, `completed`, `partial`, `failed`

### Items_AgentRunOut_

| Field | Type | Required | Description |
|---|---|---|---|
| `items` | array of [AgentRunOut](#agentrunout) | yes |  |

### Items_EvidenceOut_

| Field | Type | Required | Description |
|---|---|---|---|
| `items` | array of [EvidenceOut](#evidenceout) | yes |  |

### Items_ProposalOut_

| Field | Type | Required | Description |
|---|---|---|---|
| `items` | array of [ProposalOut](#proposalout) | yes |  |

### MeResponse

| Field | Type | Required | Description |
|---|---|---|---|
| `id` | string (uuid) | yes |  |
| `email` | string or null | yes |  |
| `display_name` | string | yes |  |
| `organization` | [OrganizationRef](#organizationref) | yes |  |
| `roles` | array of [Role](#role) | yes |  |
| `permissions` | array of [Permission](#permission) | yes |  |

### ModelList

| Field | Type | Required | Description |
|---|---|---|---|
| `items` | array of [ModelOut](#modelout) | yes |  |

### ModelOut

| Field | Type | Required | Description |
|---|---|---|---|
| `id` | string (uuid) | yes |  |
| `name` | string | yes |  |
| `version` | integer | yes |  |
| `status` | string | yes |  |
| `feature_schema` | object | yes |  |
| `metrics` | object | yes |  |
| `mlflow_run_id` | string or null | yes |  |
| `created_at` | string (date-time) | yes |  |
| `promoted_at` | string (date-time) or null | yes |  |

### OrganizationRef

| Field | Type | Required | Description |
|---|---|---|---|
| `id` | string (uuid) | yes |  |
| `slug` | string | yes |  |

### Permission

One of: `view_services`, `view_incidents`, `start_investigation`, `approve_remediation`, `manage_users`, `manage_runbooks`, `view_audit_logs`, `manage_services`, `manage_incidents`, `manage_models`

### PostmortemOut

| Field | Type | Required | Description |
|---|---|---|---|
| `id` | string (uuid) | yes |  |
| `status` | string | yes |  |
| `content` | object or null | yes |  |
| `generated_by` | string or null | yes |  |
| `prompt_version` | string or null | yes |  |
| `updated_at` | string (date-time) | yes |  |

### ProposalOut

| Field | Type | Required | Description |
|---|---|---|---|
| `id` | string (uuid) | yes |  |
| `action_type` | [RemediationAction](#remediationaction) | yes |  |
| `description` | string | yes |  |
| `parameters` | object | yes |  |
| `risk_level` | string | yes |  |
| `status` | [ProposalStatus](#proposalstatus) | yes |  |
| `verification_plan` | object | yes |  |
| `evidence_ids` | array of string | yes |  |
| `runbook_id` | string (uuid) or null | yes |  |
| `version` | integer | yes |  |
| `expires_at` | string (date-time) or null | yes |  |
| `created_at` | string (date-time) | yes |  |
| `decision` | [DecisionOut](#decisionout) or null | no |  |
| `execution` | [ExecutionOut](#executionout) or null | no |  |

### ProposalStatus

One of: `PENDING`, `APPROVED`, `REJECTED`, `EXECUTING`, `EXECUTED`, `FAILED`, `SUPERSEDED`, `EXPIRED`

### ReadinessResponse

| Field | Type | Required | Description |
|---|---|---|---|
| `status` | `ready` / `not_ready` | yes |  |
| `checks` | object | yes |  |

### ReindexResult

| Field | Type | Required | Description |
|---|---|---|---|
| `reindexed` | integer | yes |  |
| `chunks` | integer | yes |  |

### RemediationAction

One of: `ROLLBACK_DEPLOYMENT`, `RESTART_DEPLOYMENT`, `SCALE_DEPLOYMENT`, `PAUSE_ROLLOUT`, `NO_ACTION`

### RemediationMetrics

| Field | Type | Required | Description |
|---|---|---|---|
| `decisions` | integer | yes | Human approve/reject decisions recorded in the range |
| `approval_rate` | number or null | yes | Share of those decisions that approved |

### ResponseMetrics

| Field | Type | Required | Description |
|---|---|---|---|
| `mtta_seconds` | number or null | yes | Mean acknowledged_at - started_at over incidents started in the range |
| `mttr_seconds` | number or null | yes | Mean resolved_at - started_at over incidents started in the range that are resolved |

### Role

One of: `viewer`, `operator`, `incident-commander`, `administrator`

### RunbookCreate

| Field | Type | Required | Description |
|---|---|---|---|
| `content` | string | yes |  |
| `source_url` | string (uri) or null | no |  |
| `slug` | string or null | no |  |

### RunbookHitOut

One retrieved section with its citation. `content` is untrusted text.

| Field | Type | Required | Description |
|---|---|---|---|
| `runbook_id` | string (uuid) | yes |  |
| `runbook_slug` | string | yes |  |
| `title` | string | yes |  |
| `heading` | string | yes |  |
| `content` | string | yes |  |
| `score` | number | yes |  |
| `version` | integer | yes |  |
| `source_url` | string or null | yes |  |
| `flagged` | boolean | yes |  |

### RunbookHits

| Field | Type | Required | Description |
|---|---|---|---|
| `items` | array of [RunbookHitOut](#runbookhitout) | yes |  |

### RunbookList

| Field | Type | Required | Description |
|---|---|---|---|
| `items` | array of [RunbookSummary](#runbooksummary) | yes |  |

### RunbookOut

| Field | Type | Required | Description |
|---|---|---|---|
| `id` | string (uuid) | yes |  |
| `slug` | string | yes |  |
| `title` | string | yes |  |
| `services` | array of string | yes |  |
| `environment` | string | yes |  |
| `owner` | string or null | yes |  |
| `version` | integer | yes |  |
| `status` | [RunbookStatus](#runbookstatus) | yes |  |
| `source_url` | string or null | yes |  |
| `updated_at` | string (date-time) | yes |  |
| `content` | string | yes |  |
| `sections` | array of [SectionOut](#sectionout) | yes |  |

### RunbookStatus

One of: `active`, `archived`

### RunbookSummary

| Field | Type | Required | Description |
|---|---|---|---|
| `id` | string (uuid) | yes |  |
| `slug` | string | yes |  |
| `title` | string | yes |  |
| `services` | array of string | yes |  |
| `environment` | string | yes |  |
| `owner` | string or null | yes |  |
| `version` | integer | yes |  |
| `status` | [RunbookStatus](#runbookstatus) | yes |  |
| `source_url` | string or null | yes |  |
| `updated_at` | string (date-time) | yes |  |

### RunbookWrite

| Field | Type | Required | Description |
|---|---|---|---|
| `content` | string | yes |  |
| `source_url` | string (uri) or null | no |  |

### Score

| Field | Type | Required | Description |
|---|---|---|---|
| `time` | string (date-time) | yes |  |
| `service` | string | yes |  |
| `score` | number | yes |  |
| `alert` | boolean | yes |  |

### ScoreIn

| Field | Type | Required | Description |
|---|---|---|---|
| `windows` | array of [Window](#window) | yes |  |

### ScoreOut

| Field | Type | Required | Description |
|---|---|---|---|
| `model` | string | yes |  |
| `threshold` | number | yes |  |
| `scores` | array of [Score](#score) | yes |  |

### SectionOut

| Field | Type | Required | Description |
|---|---|---|---|
| `heading` | string | yes |  |
| `body` | string | yes |  |

### ServiceComparison

| Field | Type | Required | Description |
|---|---|---|---|
| `service_id` | string (uuid) | yes |  |
| `service` | string | yes |  |
| `shadow_windows` | integer | yes |  |
| `shadow_alerts` | integer | yes |  |
| `rule_triggers` | integer | yes |  |
| `incidents` | integer | yes |  |

### ServiceCreate

| Field | Type | Required | Description |
|---|---|---|---|
| `description` | string or null | no |  |
| `owner_team` | string or null | no |  |
| `repository_url` | string (uri) or null | no |  |
| `namespace` | string or null | no |  |
| `deployment_name` | string or null | no |  |
| `name` | string | yes |  |
| `slug` | string | yes |  |

### ServiceList

| Field | Type | Required | Description |
|---|---|---|---|
| `items` | array of [ServiceOut](#serviceout) | yes |  |

### ServiceOut

| Field | Type | Required | Description |
|---|---|---|---|
| `id` | string (uuid) | yes |  |
| `name` | string | yes |  |
| `slug` | string | yes |  |
| `description` | string or null | yes |  |
| `owner_team` | string or null | yes |  |
| `repository_url` | string or null | yes |  |
| `namespace` | string or null | yes |  |
| `deployment_name` | string or null | yes |  |
| `health_status` | [HealthStatus](#healthstatus) | yes |  |
| `created_at` | string (date-time) | yes |  |
| `updated_at` | string (date-time) | yes |  |

### ServiceUpdate

| Field | Type | Required | Description |
|---|---|---|---|
| `description` | string or null | no |  |
| `owner_team` | string or null | no |  |
| `repository_url` | string (uri) or null | no |  |
| `namespace` | string or null | no |  |
| `deployment_name` | string or null | no |  |
| `name` | string or null | no |  |
| `slug` | string or null | no |  |

### Severity

One of: `critical`, `high`, `medium`, `low`

### SeverityCounts

| Field | Type | Required | Description |
|---|---|---|---|
| `critical` | integer | no |  |
| `high` | integer | no |  |
| `medium` | integer | no |  |
| `low` | integer | no |  |

### ShadowSummary

| Field | Type | Required | Description |
|---|---|---|---|
| `since` | string (date-time) | yes |  |
| `model` | string or null | yes |  |
| `services` | array of [ServiceComparison](#servicecomparison) | yes |  |
| `features` | array of string | no |  |

### ToolCallOut

| Field | Type | Required | Description |
|---|---|---|---|
| `id` | string (uuid) | yes |  |
| `tool_name` | string | yes |  |
| `arguments` | object | yes |  |
| `status` | string | yes |  |
| `result_summary` | string or null | yes |  |
| `error` | string or null | yes |  |
| `duration_ms` | number | yes |  |
| `created_at` | string (date-time) | yes |  |

### Topology

| Field | Type | Required | Description |
|---|---|---|---|
| `nodes` | array of [TopologyNode](#topologynode) | yes |  |
| `edges` | array of [TopologyEdge](#topologyedge) | yes |  |

### TopologyEdge

| Field | Type | Required | Description |
|---|---|---|---|
| `source_id` | string (uuid) | yes |  |
| `target_id` | string (uuid) | yes |  |

### TopologyNode

| Field | Type | Required | Description |
|---|---|---|---|
| `id` | string (uuid) | yes |  |
| `name` | string | yes |  |
| `slug` | string | yes |  |
| `health_status` | [HealthStatus](#healthstatus) | yes |  |
| `active_incidents` | integer | yes |  |
| `investigating` | boolean | yes |  |

### UserItem

| Field | Type | Required | Description |
|---|---|---|---|
| `id` | string (uuid) | yes |  |
| `email` | string or null | yes |  |
| `display_name` | string | yes |  |
| `status` | [UserStatus](#userstatus) | yes |  |
| `roles` | array of [Role](#role) | yes | Realm roles from the user's latest sign-in |
| `permissions` | array of [Permission](#permission) | yes | What those roles allow in OpsPilot |
| `created_at` | string (date-time) | yes | First sign-in |
| `updated_at` | string (date-time) | yes |  |

### UserPage

| Field | Type | Required | Description |
|---|---|---|---|
| `items` | array of [UserItem](#useritem) | yes |  |
| `next_cursor` | string or null | yes |  |

### UserStatus

One of: `active`, `disabled`

### ValidationError

| Field | Type | Required | Description |
|---|---|---|---|
| `loc` | array of string or integer | yes |  |
| `msg` | string | yes |  |
| `type` | string | yes |  |
| `input` | object | no |  |
| `ctx` | object | no |  |

### VersionedRequest

| Field | Type | Required | Description |
|---|---|---|---|
| `version` | integer | yes |  |

### Window

One 15 s feature window of one service (feature schema v1).

| Field | Type | Required | Description |
|---|---|---|---|
| `time` | string (date-time) | yes |  |
| `service` | string | yes |  |
| `request_rate` | number or null | no |  |
| `error_rate` | number or null | no |  |
| `p50_seconds` | number or null | no |  |
| `p95_seconds` | number or null | no |  |
| `p99_seconds` | number or null | no |  |
| `restarts_5m` | number or null | no |  |
| `availability` | number or null | no |  |
