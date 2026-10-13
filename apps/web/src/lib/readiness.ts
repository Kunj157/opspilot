import { createApiClient, type CheckResult, type ReadinessResponse } from "@opspilot/api-client";

export type ReadinessResult =
  | { reachable: true; readiness: ReadinessResponse }
  | { reachable: false };

export type Tone = "healthy" | "degraded" | "critical" | "unknown";

function isReadinessResponse(value: unknown): value is ReadinessResponse {
  return typeof value === "object" && value !== null && "checks" in value && "status" in value;
}

/**
 * Fetches API readiness. Never throws: a network failure or an unexpected
 * response means the API itself is unreachable, which is a state to render,
 * not an error to bubble up.
 */
export async function fetchReadiness(signal?: AbortSignal): Promise<ReadinessResult> {
  const client = createApiClient(window.location.origin);
  try {
    const { data, error, response } = await client.GET("/api/v1/ready", { signal });
    if (data) return { reachable: true, readiness: data };
    if (response.status === 503 && isReadinessResponse(error)) {
      return { reachable: true, readiness: error };
    }
  } catch {
    // fall through: the API could not be reached
  }
  return { reachable: false };
}

export function describeCheck(check: CheckResult): { label: string; tone: Tone } {
  if (check.status === "ok") return { label: "Operational", tone: "healthy" };
  if (check.detail === "timeout") return { label: "Timed out", tone: "degraded" };
  if (check.detail?.startsWith("missing")) return { label: "Misconfigured", tone: "critical" };
  return { label: "Unavailable", tone: "critical" };
}
