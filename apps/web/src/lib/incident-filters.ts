/**
 * Incident list filters, kept in the URL so a filtered view can be shared
 * and survives reloads. Unknown or malformed values are dropped rather than
 * sent to the API.
 */
import type { components, paths } from "@opspilot/api-client/schema";

export type Severity = components["schemas"]["Severity"];
export type IncidentStatus = components["schemas"]["IncidentStatus"];
export type Source = "manual" | "detector" | "alertmanager";

export const STATUSES: IncidentStatus[] = [
  "DETECTED",
  "INVESTIGATING",
  "AWAITING_APPROVAL",
  "REMEDIATING",
  "VERIFYING",
  "MONITORING",
  "REJECTED",
  "RESOLVED",
];
export const ACTIVE_STATUSES = STATUSES.filter((s) => s !== "RESOLVED");
export const SEVERITIES: Severity[] = ["critical", "high", "medium", "low"];
export const SOURCES: Source[] = ["manual", "detector", "alertmanager"];

export type StatusFilter = "active" | "all" | IncidentStatus;

export type IncidentFilters = {
  status: StatusFilter;
  severity: Severity[];
  service: string | null;
  source: Source | null;
  since: string | null;
  until: string | null;
  mine: boolean;
};

const DATE = /^\d{4}-\d{2}-\d{2}$/;
const ID = /^[0-9a-f-]{1,36}$/i;

function oneOf<T extends string>(values: readonly T[], value: string | null): T | null {
  return values.includes(value as T) ? (value as T) : null;
}

function date(value: string | null): string | null {
  return value && DATE.test(value) && !Number.isNaN(Date.parse(value)) ? value : null;
}

export function parseFilters(params: URLSearchParams): IncidentFilters {
  const status = params.get("status");
  const service = params.get("service");
  return {
    status: status === "all" ? "all" : (oneOf(STATUSES, status) ?? "active"),
    severity: SEVERITIES.filter((s) => params.getAll("severity").includes(s)),
    service: service && ID.test(service) ? service : null,
    source: oneOf(SOURCES, params.get("source")),
    since: date(params.get("since")),
    until: date(params.get("until")),
    mine: params.get("mine") === "1",
  };
}

export function filtersToSearch(filters: IncidentFilters): string {
  const params = new URLSearchParams();
  if (filters.status !== "active") params.set("status", filters.status);
  for (const severity of filters.severity) params.append("severity", severity);
  if (filters.service) params.set("service", filters.service);
  if (filters.source) params.set("source", filters.source);
  if (filters.since) params.set("since", filters.since);
  if (filters.until) params.set("until", filters.until);
  if (filters.mine) params.set("mine", "1");
  const search = params.toString();
  return search ? `?${search}` : "";
}

type ListQuery = NonNullable<paths["/api/v1/incidents"]["get"]["parameters"]["query"]>;

/** Local calendar day → ISO instant; `until` includes the whole day. */
function dayStart(value: string, offsetDays = 0): string {
  const [y, m, d] = value.split("-").map(Number);
  return new Date(y, m - 1, d + offsetDays).toISOString();
}

export function toApiQuery(filters: IncidentFilters, currentUserId: string): ListQuery {
  const query: ListQuery = {};
  if (filters.status === "active") query.status = ACTIVE_STATUSES;
  else if (filters.status !== "all") query.status = [filters.status];
  if (filters.severity.length) query.severity = filters.severity;
  if (filters.service) query.service_id = filters.service;
  if (filters.source) query.source = filters.source;
  if (filters.since) query.since = dayStart(filters.since);
  if (filters.until) query.until = dayStart(filters.until, 1);
  if (filters.mine) query.assigned_user_id = currentUserId;
  return query;
}
