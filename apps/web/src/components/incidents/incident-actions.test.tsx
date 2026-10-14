import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, describe, expect, it, vi } from "vitest";

import { availableActions, IncidentActions } from "./incident-actions";
import { formatDuration } from "./incident-detail";

function incident(overrides: Record<string, unknown> = {}) {
  return {
    id: "00000000-0000-4000-8000-000000000001",
    title: "Checkout 500s",
    description: null,
    severity: "high",
    status: "DETECTED",
    source: "manual",
    service_id: null,
    started_at: "2026-10-13T12:00:00Z",
    acknowledged_at: null,
    resolved_at: null,
    detection_score: null,
    assigned_user_id: null,
    version: 3,
    created_at: "2026-10-13T12:00:00Z",
    updated_at: "2026-10-13T12:00:00Z",
    allowed_transitions: ["INVESTIGATING"],
    ...overrides,
  } as Parameters<typeof availableActions>[0];
}

const ALL = { manage: true, investigate: true };
const keys = (i: ReturnType<typeof incident>, p = ALL) => availableActions(i, p).map((a) => a.key);

function json(body: unknown, status: number) {
  return new Response(JSON.stringify(body), { status, headers: { "Content-Type": "application/json" } });
}

afterEach(() => vi.unstubAllGlobals());

describe("availableActions", () => {
  it("offers acknowledge and investigation on a new incident", () => {
    expect(keys(incident())).toEqual(["acknowledge", "investigate"]);
  });

  it("follows the allowed transitions", () => {
    const investigating = incident({
      status: "INVESTIGATING",
      acknowledged_at: "x",
      allowed_transitions: ["AWAITING_APPROVAL", "MONITORING"],
    });
    const monitoring = incident({ status: "MONITORING", acknowledged_at: "x", allowed_transitions: ["RESOLVED"] });

    expect(keys(investigating)).toEqual(["monitor"]);
    expect(keys(monitoring)).toEqual(["resolve"]);
    expect(keys(incident({ status: "RESOLVED", allowed_transitions: [] }))).toEqual([]);
  });

  it("respects permissions", () => {
    expect(keys(incident(), { manage: false, investigate: false })).toEqual([]);
    expect(keys(incident(), { manage: false, investigate: true })).toEqual(["investigate"]);
  });
});

describe("IncidentActions", () => {
  it("sends the expected version and reports the updated incident", async () => {
    const updated = incident({ status: "INVESTIGATING", version: 4 });
    const fetchMock = vi.fn<(r: Request) => Promise<Response>>(async () => json(updated, 200));
    vi.stubGlobal("fetch", fetchMock);
    const onChanged = vi.fn();

    render(<IncidentActions incident={incident()} permissions={ALL} onChanged={onChanged} onConflict={vi.fn()} />);
    await userEvent.click(screen.getByRole("button", { name: "Start investigation" }));

    const request = fetchMock.mock.calls[0][0];
    expect(new URL(request.url).pathname).toBe("/api/v1/incidents/00000000-0000-4000-8000-000000000001/investigate");
    expect(await request.json()).toEqual({ version: 3 });
    expect(onChanged).toHaveBeenCalledWith(updated);
  });

  it("explains a stale version and asks for a refresh", async () => {
    vi.stubGlobal(
      "fetch",
      vi.fn(async () => json({ detail: { code: "stale_version", message: "x", current_version: 4 } }, 409)),
    );
    const onConflict = vi.fn();

    render(<IncidentActions incident={incident()} permissions={ALL} onChanged={vi.fn()} onConflict={onConflict} />);
    await userEvent.click(screen.getByRole("button", { name: "Acknowledge" }));

    expect(screen.getByRole("alert")).toHaveTextContent(/someone else changed this incident/i);
    expect(onConflict).toHaveBeenCalled();
  });

  it("renders nothing when no action is available", () => {
    const { container } = render(
      <IncidentActions
        incident={incident({ status: "RESOLVED", allowed_transitions: [] })}
        permissions={ALL}
        onChanged={vi.fn()}
        onConflict={vi.fn()}
      />,
    );
    expect(container).toBeEmptyDOMElement();
  });
});

describe("formatDuration", () => {
  it("formats minutes, hours, and days", () => {
    const start = "2026-10-13T12:00:00Z";
    expect(formatDuration(start, new Date("2026-10-13T12:07:30Z"))).toBe("7m");
    expect(formatDuration(start, new Date("2026-10-13T15:12:00Z"))).toBe("3h 12m");
    expect(formatDuration(start, new Date("2026-10-15T14:00:00Z"))).toBe("2d 2h");
    expect(formatDuration(start, new Date("2026-10-13T11:00:00Z"))).toBe("0m");
  });
});
