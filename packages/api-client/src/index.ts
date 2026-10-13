import createClient from "openapi-fetch";

import type { components, paths } from "./schema";

export type ReadinessResponse = components["schemas"]["ReadinessResponse"];
export type CheckResult = components["schemas"]["CheckResult"];

export function createApiClient(baseUrl: string) {
  return createClient<paths>({ baseUrl });
}

export type ApiClient = ReturnType<typeof createApiClient>;
