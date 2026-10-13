import { act, renderHook } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { useIncidentStream } from "./use-incident-stream";

class FakeEventSource {
  static CONNECTING = 0;
  static OPEN = 1;
  static CLOSED = 2;
  static instances: FakeEventSource[] = [];

  readyState = FakeEventSource.CONNECTING;
  onopen: (() => void) | null = null;
  onerror: (() => void) | null = null;
  listeners = new Map<string, (event: MessageEvent<string>) => void>();
  closed = false;

  constructor(public url: string) {
    FakeEventSource.instances.push(this);
  }
  addEventListener(type: string, listener: (event: MessageEvent<string>) => void) {
    this.listeners.set(type, listener);
  }
  close() {
    this.closed = true;
    this.readyState = FakeEventSource.CLOSED;
  }
  emit(type: string, data: string) {
    this.listeners.get(type)?.(new MessageEvent(type, { data }));
  }
}

beforeEach(() => {
  FakeEventSource.instances = [];
  vi.stubGlobal("EventSource", FakeEventSource);
});
afterEach(() => {
  vi.unstubAllGlobals();
  vi.useRealTimers();
});

const event = { id: "e1", sequence: 7, event_type: "incident.created", incident: { id: "i1", version: 1 } };

describe("useIncidentStream", () => {
  it("reports live once connected and delivers named incident events", () => {
    const onEvent = vi.fn();
    const { result } = renderHook(() => useIncidentStream("/api/v1/incidents/stream", onEvent));
    const source = FakeEventSource.instances[0];
    expect(result.current).toBe("connecting");

    act(() => source.onopen?.());
    act(() => source.emit("incident.created", JSON.stringify(event)));

    expect(result.current).toBe("live");
    expect(onEvent).toHaveBeenCalledWith(event);
  });

  it("skips malformed frames", () => {
    const onEvent = vi.fn();
    renderHook(() => useIncidentStream("/s", onEvent));

    act(() => FakeEventSource.instances[0].emit("incident.updated", "{not json"));

    expect(onEvent).not.toHaveBeenCalled();
  });

  it("shows reconnecting while the browser retries, and reopens a closed stream", () => {
    vi.useFakeTimers();
    const { result } = renderHook(() => useIncidentStream("/s", vi.fn()));
    const first = FakeEventSource.instances[0];

    first.readyState = FakeEventSource.CLOSED;
    act(() => first.onerror?.());
    expect(result.current).toBe("reconnecting");

    act(() => vi.advanceTimersByTime(5_000));
    expect(FakeEventSource.instances).toHaveLength(2);
  });

  it("closes the stream on unmount", () => {
    const { unmount } = renderHook(() => useIncidentStream("/s", vi.fn()));

    unmount();

    expect(FakeEventSource.instances[0].closed).toBe(true);
  });

  it("does not connect without a path", () => {
    renderHook(() => useIncidentStream(null, vi.fn()));

    expect(FakeEventSource.instances).toHaveLength(0);
  });
});
