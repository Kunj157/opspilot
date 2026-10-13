import { describe, expect, it } from "vitest";

import { clientAddress, upstreamHeaders } from "./forwarding";

describe("clientAddress", () => {
  it("forwards nothing without a trusted proxy in front, because the header may be forged", () => {
    expect(clientAddress("1.2.3.4", 0)).toBeNull();
  });

  it("takes the address appended by a single trusted ingress", () => {
    expect(clientAddress("198.51.100.23", 1)).toBe("198.51.100.23");
  });

  it("ignores a forged prefix the browser sent itself", () => {
    expect(clientAddress("1.2.3.4, 198.51.100.23", 1)).toBe("198.51.100.23");
  });

  it("skips the address of an inner trusted proxy", () => {
    expect(clientAddress("1.2.3.4, 198.51.100.23, 10.0.0.9", 2)).toBe("198.51.100.23");
  });

  it("forwards nothing when the chain is shorter than the trusted hops", () => {
    expect(clientAddress("198.51.100.23", 2)).toBeNull();
    expect(clientAddress(null, 1)).toBeNull();
    expect(clientAddress(" , ", 1)).toBeNull();
  });
});

describe("upstreamHeaders", () => {
  const incoming = new Headers({
    accept: "application/json",
    "content-type": "application/json",
    "x-request-id": "req-1",
    "x-forwarded-for": "1.2.3.4, 198.51.100.23",
    cookie: "opspilot_session=secret",
    authorization: "Bearer from-the-browser",
    host: "localhost:3000",
  });

  it("forwards allow-listed headers, the session token, and the trusted client address", () => {
    expect(Object.fromEntries(upstreamHeaders(incoming, "session-token", 1))).toEqual({
      accept: "application/json",
      "content-type": "application/json",
      "x-request-id": "req-1",
      "x-forwarded-for": "198.51.100.23",
      authorization: "Bearer session-token",
    });
  });

  it("drops the client address when no proxy is trusted", () => {
    expect(upstreamHeaders(incoming, "session-token", 0).has("x-forwarded-for")).toBe(false);
  });

  it("never passes the browser's own authorization header", () => {
    const headers = upstreamHeaders(new Headers({ authorization: "Bearer forged" }), null, 1);
    expect(headers.has("authorization")).toBe(false);
  });
});
