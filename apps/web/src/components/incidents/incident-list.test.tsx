import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { act, render, screen, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { ToastProvider } from "@/components/ui/toast";

import { IncidentList } from "./incident-list";

const navigation = vi.hoisted(() => ({ search: "", replace: vi.fn() }));
vi.mock("next/navigation", () => ({
  useRouter: () => ({ replace: navigation.replace, push: vi.fn() }),
  usePathname: () => "/incidents",
  useSearchParams: () => new URLSearchParams(navigation.search),
}));

class FakeEventSource {
  static CLOSED = 2;
  static last: FakeEventSource;
  listeners = new Map<string, (event: MessageEvent<string>) => void>();
  onopen: (() => void) | null = null;
  onerror: (() => void) | null = null;
  constructor(public url: string) {
    FakeEventSource.last = this;
  }
  addEventListener(type: string, listener: (event: MessageEvent<string>) => void) {
    this.listeners.set(type, listener);
  }
  close() {}
}

function incident(n: number, overrides: Record<string, unknown> = {}) {
  return {
    id: `00000000-0000-4000-8000-${String(n).padStart(12, "0")}`,
    title: `Incident ${n}`,
    description: null,
    severity: "high",
    status: "DETECTED",
    source: "manual",
    service_id: "svc-1",
    started_at: "2026-10-13T12:00:00Z",
    acknowledged_at: null,
    resolved_at: null,
    detection_score: null,
    assigned_user_id: null,
    version: 1,
    created_at: "2026-10-13T12:00:00Z",
    updated_at: "2026-10-13T12:00:00Z",
    allowed_transitions: [],
    ...overrides,
  };
}

let incidents: ReturnType<typeof incident>[];
const requests: URL[] = [];

beforeEach(() => {
  navigation.search = "";
  navigation.replace.mockReset();
  requests.length = 0;
  incidents = [incident(1)];
  vi.stubGlobal("EventSource", FakeEventSource);
  vi.stubGlobal(
    "fetch",
    vi.fn(async (input: Request) => {
      const url = new URL(input.url);
      requests.push(url);
      const body =
        url.pathname === "/api/v1/services"
          ? { items: [{ id: "svc-1", name: "Checkout" }] }
          : { items: incidents, next_cursor: null };
      return new Response(JSON.stringify(body), { headers: { "Content-Type": "application/json" } });
    }),
  );
});
afterEach(() => vi.unstubAllGlobals());

function renderIt(canManage = true) {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(
    <QueryClientProvider client={client}>
      <ToastProvider>
        <IncidentList canManage={canManage} currentUserId="user-1" />
      </ToastProvider>
    </QueryClientProvider>,
  );
}

describe("IncidentList", () => {
  it("lists incidents with severity, service, and status", async () => {
    renderIt();

    const row = (await screen.findByText("Incident 1", { exact: true })).closest("tr")!;
    expect(within(row).getByText("High")).toBeInTheDocument();
    expect(await within(row).findByText("Checkout")).toBeInTheDocument();
    expect(within(row).getAllByText("Detected").length).toBeGreaterThan(0);
  });

  it("queries the API with the filters from the URL", async () => {
    navigation.search = "status=all&severity=critical&mine=1";
    renderIt();
    await screen.findByText("Incident 1", { exact: true });

    const list = requests.find((u) => u.pathname === "/api/v1/incidents")!;
    expect(list.searchParams.getAll("status")).toEqual([]);
    expect(list.searchParams.getAll("severity")).toEqual(["critical"]);
    expect(list.searchParams.get("assigned_user_id")).toBe("user-1");
  });

  it("writes a changed filter to the URL", async () => {
    renderIt();
    await screen.findByText("Incident 1", { exact: true });

    await userEvent.selectOptions(screen.getByLabelText("Severity"), "critical");

    expect(navigation.replace).toHaveBeenCalledWith("/incidents?severity=critical", { scroll: false });
  });

  it("shows a new incident when the stream reports one", async () => {
    renderIt();
    await screen.findByText("Incident 1", { exact: true });

    incidents = [incident(2, { title: "Checkout 500s" }), incident(1)];
    act(() => {
      FakeEventSource.last.onopen?.();
      FakeEventSource.last.listeners.get("incident.created")?.(
        new MessageEvent("incident.created", { data: JSON.stringify({ incident: { id: "x", version: 1 } }) }),
      );
    });

    expect(await screen.findByText("Checkout 500s", { exact: true })).toBeInTheDocument();
    expect(screen.getByRole("status")).toHaveTextContent("Live");
  });

  it("explains an empty filtered view", async () => {
    navigation.search = "severity=low";
    incidents = [];
    renderIt();

    expect(await screen.findByText("No incidents match these filters.")).toBeInTheDocument();
  });

  it("hides creation from users who cannot manage incidents", async () => {
    renderIt(false);
    await screen.findByText("Incident 1", { exact: true });

    expect(screen.queryByRole("button", { name: "New incident" })).not.toBeInTheDocument();
  });
});
