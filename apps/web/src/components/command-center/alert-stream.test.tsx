import { act, render, screen, within } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { AlertStream } from "./alert-stream";

class FakeEventSource {
  static last: FakeEventSource;
  readyState = 1;
  onopen: (() => void) | null = null;
  onerror: (() => void) | null = null;
  listeners = new Map<string, (e: MessageEvent<string>) => void>();
  constructor(public url: string) {
    FakeEventSource.last = this;
  }
  addEventListener(type: string, fn: (e: MessageEvent<string>) => void) {
    this.listeners.set(type, fn);
  }
  close() {}
  emit(type: string, data: unknown) {
    this.listeners.get(type)?.(new MessageEvent(type, { data: JSON.stringify(data) }));
  }
}

function frame(sequence: number, type: string, title: string, severity = "critical") {
  return {
    id: `e${sequence}`,
    sequence,
    event_type: type,
    title,
    created_at: "2026-10-13T12:00:00Z",
    incident: { id: `i${sequence}`, version: 1, title: `Incident ${sequence}`, severity },
  };
}

beforeEach(() => vi.stubGlobal("EventSource", FakeEventSource));
afterEach(() => vi.unstubAllGlobals());

describe("AlertStream", () => {
  it("starts empty and listens to the organization stream", () => {
    render(<AlertStream onEvent={() => {}} />);

    expect(FakeEventSource.last.url).toBe("/api/v1/incidents/stream");
    expect(screen.getByText(/no new alerts/i)).toBeInTheDocument();
  });

  it("shows new events first, keeps the latest eight, and reports each one", () => {
    const onEvent = vi.fn();
    render(<AlertStream onEvent={onEvent} />);

    act(() => {
      for (let i = 1; i <= 10; i++) FakeEventSource.last.emit("incident.created", frame(i, "incident.created", "Incident detected"));
    });

    const items = within(screen.getByRole("list", { name: "Live alerts" })).getAllByRole("listitem");
    expect(items).toHaveLength(8);
    expect(items[0]).toHaveTextContent("Incident 10");
    expect(within(items[0]).getByRole("link", { name: "Incident 10" })).toHaveAttribute("href", "/incidents/i10");
    expect(onEvent).toHaveBeenCalledTimes(10);
  });

  it("ignores a repeated event", () => {
    render(<AlertStream onEvent={() => {}} />);

    act(() => {
      FakeEventSource.last.emit("incident.created", frame(1, "incident.created", "Incident detected"));
      FakeEventSource.last.emit("incident.created", frame(1, "incident.created", "Incident detected"));
    });

    expect(within(screen.getByRole("list", { name: "Live alerts" })).getAllByRole("listitem")).toHaveLength(1);
  });
});
