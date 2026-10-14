import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, describe, expect, it, vi } from "vitest";

import { ServiceForm } from "./service-form";

function json(body: unknown, status: number) {
  return new Response(JSON.stringify(body), { status, headers: { "Content-Type": "application/json" } });
}

afterEach(() => vi.unstubAllGlobals());

describe("ServiceForm", () => {
  it("suggests a slug from the name until the slug is edited", async () => {
    render(<ServiceForm onSaved={vi.fn()} />);

    await userEvent.type(screen.getByLabelText("Name"), "Checkout API");
    expect(screen.getByLabelText("Slug")).toHaveValue("checkout-api");

    await userEvent.clear(screen.getByLabelText("Slug"));
    await userEvent.type(screen.getByLabelText("Slug"), "checkout");
    await userEvent.type(screen.getByLabelText("Name"), " v2");
    expect(screen.getByLabelText("Slug")).toHaveValue("checkout");
  });

  it("creates a service with an idempotency key and reports it", async () => {
    const created = { id: "svc-1", name: "Checkout", slug: "checkout" };
    const fetchMock = vi.fn<(input: Request) => Promise<Response>>(async () => json(created, 201));
    vi.stubGlobal("fetch", fetchMock);
    const onSaved = vi.fn();

    render(<ServiceForm onSaved={onSaved} />);
    await userEvent.type(screen.getByLabelText("Name"), "Checkout");
    await userEvent.type(screen.getByLabelText("Owner team"), "payments");
    await userEvent.click(screen.getByRole("button", { name: "Create service" }));

    expect(onSaved).toHaveBeenCalledWith(created);
    const request = fetchMock.mock.calls[0][0];
    expect(request.method).toBe("POST");
    expect(request.headers.get("Idempotency-Key")).toMatch(/^[0-9a-f-]{36}$/);
    expect(await request.json()).toEqual({ name: "Checkout", slug: "checkout", owner_team: "payments" });
  });

  it("shows server validation errors next to the field", async () => {
    vi.stubGlobal(
      "fetch",
      vi.fn(async () =>
        json({ detail: [{ loc: ["body", "namespace"], msg: "Namespace is reserved", type: "x" }] }, 422),
      ),
    );

    render(<ServiceForm onSaved={vi.fn()} />);
    await userEvent.type(screen.getByLabelText("Name"), "Checkout");
    await userEvent.type(screen.getByLabelText("Namespace"), "kube-system");
    await userEvent.click(screen.getByRole("button", { name: "Create service" }));

    const namespace = await screen.findByLabelText("Namespace");
    expect(namespace).toHaveAttribute("aria-invalid", "true");
    expect(namespace).toHaveAccessibleDescription(/reserved/i);
  });

  it("explains invalid values before sending anything", async () => {
    const fetchMock = vi.fn();
    vi.stubGlobal("fetch", fetchMock);

    render(<ServiceForm onSaved={vi.fn()} />);
    await userEvent.type(screen.getByLabelText("Name"), "Checkout");
    await userEvent.type(screen.getByLabelText("Namespace"), "Bad_NS");
    await userEvent.click(screen.getByRole("button", { name: "Create service" }));

    expect(await screen.findByLabelText("Namespace")).toHaveAccessibleDescription(/lowercase/i);
    expect(fetchMock).not.toHaveBeenCalled();
  });

  it("explains a slug that is already taken", async () => {
    vi.stubGlobal(
      "fetch",
      vi.fn(async () => json({ detail: "A service with this slug already exists" }, 409)),
    );

    render(<ServiceForm onSaved={vi.fn()} />);
    await userEvent.type(screen.getByLabelText("Name"), "Checkout");
    await userEvent.click(screen.getByRole("button", { name: "Create service" }));

    expect(screen.getByLabelText("Slug")).toHaveAccessibleDescription(/already exists/);
  });

  it("edits only the changed fields of an existing service", async () => {
    const service = {
      id: "svc-1",
      name: "Checkout",
      slug: "checkout",
      description: null,
      owner_team: "payments",
      repository_url: null,
      namespace: "demo",
      deployment_name: "checkout",
    };
    const fetchMock = vi.fn<(input: Request) => Promise<Response>>(async () =>
      json({ ...service, owner_team: "core" }, 200),
    );
    vi.stubGlobal("fetch", fetchMock);

    render(<ServiceForm service={service} onSaved={vi.fn()} />);
    const owner = screen.getByLabelText("Owner team");
    await userEvent.clear(owner);
    await userEvent.type(owner, "core");
    await userEvent.click(screen.getByRole("button", { name: "Save changes" }));

    const request = fetchMock.mock.calls[0][0];
    expect(request.method).toBe("PATCH");
    expect(new URL(request.url).pathname).toBe("/api/v1/services/svc-1");
    expect(await request.json()).toEqual({ owner_team: "core" });
  });
});
