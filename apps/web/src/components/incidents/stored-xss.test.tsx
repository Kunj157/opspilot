/**
 * Stored XSS (plan §21.5): text from the API — incident fields, timeline
 * events, postmortems, runbooks — is rendered as text, never as markup.
 */
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { render, screen } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { RunbookDetail } from "@/components/runbooks/runbook-detail";
import { ToastProvider } from "@/components/ui/toast";
import { MarkdownLite } from "@/lib/markdown-lite";

import { IncidentDetail } from "./incident-detail";

const PAYLOADS = [
  "<script>window.__xss = 1</script>",
  '<img src=x onerror="window.__xss = 1">',
  "<svg onload=window.__xss=1>",
  '"><iframe src="javascript:window.__xss=1">',
  "**<b onmouseover=alert(1)>bold</b>** `<script>`",
];
const INCIDENT_ID = "00000000-0000-4000-8000-000000000001";
const RUNBOOK_ID = "00000000-0000-4000-8000-000000000002";

vi.mock("next/navigation", () => ({
  useParams: () => ({ incidentId: INCIDENT_ID, runbookId: RUNBOOK_ID }),
  useRouter: () => ({ replace: vi.fn(), push: vi.fn(), refresh: vi.fn() }),
  usePathname: () => "/",
  useSearchParams: () => new URLSearchParams(),
}));

class FakeEventSource {
  static CLOSED = 2;
  readyState = 0;
  onopen: (() => void) | null = null;
  onerror: (() => void) | null = null;
  addEventListener() {}
  close() {}
}

function serve(routes: Record<string, unknown>) {
  vi.stubGlobal(
    "fetch",
    vi.fn(async (input: Request | string) => {
      const url = new URL(typeof input === "string" ? input : input.url, "http://localhost");
      const body = routes[url.pathname];
      return new Response(JSON.stringify(body ?? { detail: "Not Found" }), {
        status: body === undefined ? 404 : 200,
        headers: { "Content-Type": "application/json" },
      });
    }),
  );
}

function renderWithClient(ui: React.ReactElement) {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(
    <QueryClientProvider client={client}>
      <ToastProvider>{ui}</ToastProvider>
    </QueryClientProvider>,
  );
}

/** No element, handler, or script URL an injected payload could have produced. */
function expectNoInjectedMarkup(container: HTMLElement) {
  expect(container.querySelector("script, iframe, img, object, embed, b[onmouseover]")).toBeNull();
  for (const element of container.querySelectorAll("*")) {
    for (const attribute of element.attributes) {
      expect(attribute.name).not.toMatch(/^on/i);
      expect(attribute.value).not.toMatch(/^\s*javascript:/i);
    }
  }
  expect((window as { __xss?: number }).__xss).toBeUndefined();
}

beforeEach(() => vi.stubGlobal("EventSource", FakeEventSource));
afterEach(() => vi.unstubAllGlobals());

describe.each(PAYLOADS)("payload %s", (payload) => {
  it("renders incident title, description, timeline, and postmortem as text", async () => {
    serve({
      [`/api/v1/incidents/${INCIDENT_ID}`]: {
        id: INCIDENT_ID,
        title: `Title ${payload}`,
        description: `Description ${payload}`,
        severity: "high",
        status: "RESOLVED",
        source: "manual",
        service_id: null,
        started_at: "2026-10-14T01:00:00Z",
        acknowledged_at: null,
        resolved_at: "2026-10-14T02:00:00Z",
        detection_score: null,
        assigned_user_id: null,
        version: 3,
        created_at: "2026-10-14T01:00:00Z",
        updated_at: "2026-10-14T02:00:00Z",
        allowed_transitions: [],
      },
      [`/api/v1/incidents/${INCIDENT_ID}/events`]: {
        items: [
          {
            id: "e-1",
            sequence: 1,
            event_type: "note",
            actor_type: "agent",
            actor_id: "agent:triage",
            title: `Event ${payload}`,
            description: `Event detail ${payload}`,
            metadata: { reason: `Reason ${payload}` },
            created_at: "2026-10-14T01:05:00Z",
          },
        ],
      },
      [`/api/v1/incidents/${INCIDENT_ID}/postmortem`]: {
        id: "pm-1",
        status: "ready",
        generated_by: "scripted",
        prompt_version: "v1",
        updated_at: "2026-10-14T02:10:00Z",
        content: {
          summary: `Summary ${payload}`,
          impact: `Impact ${payload}`,
          root_cause: { statement: `Cause ${payload}`, certainty: "confirmed", evidence: ["E1"] },
          findings: [{ statement: `Finding ${payload}`, certainty: "confirmed", evidence: ["E1"] }],
          resolution: `Resolution ${payload}`,
          follow_ups: [`Follow-up ${payload}`],
          timeline: [{ at: "2026-10-14T01:16:00Z", event: `Step ${payload}`, actor: "system" }],
          evidence: { E1: { summary: `Evidence ${payload}`, source: "prometheus" } },
        },
      },
    });

    const { container } = renderWithClient(
      <IncidentDetail permissions={{ manage: false, investigate: false, approve: false }} />,
    );

    expect(await screen.findByRole("heading", { level: 1 })).toHaveTextContent(`Title ${payload}`);
    expect(await screen.findByText(`Event ${payload}`)).toBeInTheDocument();
    expect(await screen.findByText(`Summary ${payload}`)).toBeInTheDocument();
    expect(container.textContent).toContain(`Description ${payload}`);
    expect(container.textContent).toContain(`Event detail ${payload}`);
    expect(container.textContent).toContain(`Finding ${payload}`);
    expectNoInjectedMarkup(container);
  });

  it("renders runbook markdown without raw HTML", () => {
    const { container } = render(<MarkdownLite text={`# Steps\n\n- ${payload}\n\n${payload}`} />);

    expect(container.textContent).toContain(payload.replace(/\*\*|`/g, ""));
    expectNoInjectedMarkup(container);
  });
});

describe("runbook source links", () => {
  function runbook(sourceUrl: string | null) {
    return {
      id: RUNBOOK_ID,
      slug: "checkout",
      title: "Checkout errors",
      services: ["checkout"],
      owner: "shop-team",
      version: 1,
      status: "active",
      content: "# Checkout errors\n\n## Safe actions\n\nRoll back. <script>window.__xss = 1</script>",
      sections: [
        { heading: "Safe actions <img src=x onerror=alert(1)>", body: "Roll back. <script>window.__xss = 1</script>" },
      ],
      source_url: sourceUrl,
      created_at: "2026-10-14T01:00:00Z",
      updated_at: "2026-10-14T01:00:00Z",
    };
  }

  it("links http(s) sources", async () => {
    serve({ [`/api/v1/runbooks/${RUNBOOK_ID}`]: runbook("https://git.example/runbooks/checkout.md") });

    renderWithClient(<RunbookDetail canManage={false} />);

    expect(await screen.findByRole("link", { name: /source/i })).toHaveAttribute(
      "href",
      "https://git.example/runbooks/checkout.md",
    );
  });

  it.each(["javascript:alert(1)", " JavaScript:alert(1)", "data:text/html,<script>alert(1)</script>"])(
    "never links a %s source",
    async (sourceUrl) => {
      serve({ [`/api/v1/runbooks/${RUNBOOK_ID}`]: runbook(sourceUrl) });

      const { container } = renderWithClient(<RunbookDetail canManage={false} />);

      expect(await screen.findByRole("heading", { name: "Checkout errors" })).toBeInTheDocument();
      expect(screen.queryByRole("link", { name: /source/i })).not.toBeInTheDocument();
      expectNoInjectedMarkup(container);
    },
  );
});
