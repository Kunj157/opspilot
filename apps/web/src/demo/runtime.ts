"use client";

/**
 * Demo build only: answers the app's API calls and incident streams in the
 * browser from ./scenario, so the static export on GitHub Pages works without
 * a backend. Installed when this module loads, before any component fetches.
 */
import { answer, streamSince } from "./scenario";

const API = /^\/api\/v1\//;

function install() {
  if (process.env.NEXT_PUBLIC_DEMO !== "1") return;
  if (typeof window === "undefined" || (window as { __opspilotDemo?: boolean }).__opspilotDemo) return;
  (window as { __opspilotDemo?: boolean }).__opspilotDemo = true;

  const realFetch = window.fetch.bind(window);
  window.fetch = async (input: RequestInfo | URL, init?: RequestInit) => {
    const request = input instanceof Request ? input : new Request(input, init);
    const url = new URL(request.url, window.location.origin);
    if (url.origin !== window.location.origin || !API.test(url.pathname)) return realFetch(input, init);
    const text = request.method === "GET" ? "" : await request.text();
    await new Promise((r) => setTimeout(r, 90)); // a little latency so loading states look real
    const { status, body } = answer(request.method, url.pathname, url.searchParams, text ? JSON.parse(text) : null);
    return new Response(JSON.stringify(body), { status, headers: { "Content-Type": "application/json" } });
  };

  class DemoEventSource extends EventTarget {
    static readonly CONNECTING = 0;
    static readonly OPEN = 1;
    static readonly CLOSED = 2;
    readonly CONNECTING = 0;
    readonly OPEN = 1;
    readonly CLOSED = 2;
    readyState = 0;
    readonly url: string;
    readonly withCredentials = false;
    onopen: ((e: Event) => void) | null = null;
    onerror: ((e: Event) => void) | null = null;
    onmessage: ((e: MessageEvent) => void) | null = null;
    private last = 0;
    private timer: ReturnType<typeof setInterval>;

    constructor(url: string | URL) {
      super();
      this.url = String(url);
      const incident = this.url.match(/\/incidents\/([^/]+)\/stream/)?.[1] ?? null;
      // Start after what the page already loaded, so the stream delivers only what happens next.
      this.last = streamSince(incident, 0).length;
      setTimeout(() => {
        this.readyState = 1;
        this.onopen?.(new Event("open"));
      }, 150);
      this.timer = setInterval(() => {
        for (const frame of streamSince(incident, this.last)) {
          this.last = frame.sequence;
          this.dispatchEvent(
            new MessageEvent(frame.event_type, { data: JSON.stringify(frame), lastEventId: String(frame.sequence) }),
          );
        }
      }, 1000);
    }

    close() {
      this.readyState = 2;
      clearInterval(this.timer);
    }
  }
  window.EventSource = DemoEventSource as unknown as typeof EventSource;
}

install();
