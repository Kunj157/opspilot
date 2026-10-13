import createClient from "openapi-fetch";

import type { components, paths } from "./schema";

export type ReadinessResponse = components["schemas"]["ReadinessResponse"];
export type CheckResult = components["schemas"]["CheckResult"];
export type Me = components["schemas"]["MeResponse"];
export type Permission = Me["permissions"][number];
export type Role = Me["roles"][number];
export type AuditLogPage = components["schemas"]["AuditLogPage"];
export type AuditLogItem = components["schemas"]["AuditLogItem"];

export function createApiClient(baseUrl: string) {
  return createClient<paths>({ baseUrl });
}

export type ApiClient = ReturnType<typeof createApiClient>;
