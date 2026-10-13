const FORWARDED_REQUEST_HEADERS = [
  "accept",
  "content-type",
  "idempotency-key",
  "last-event-id",
  "x-request-id",
];

/**
 * The browser's address, if it can be trusted.
 *
 * Next.js only sets X-Forwarded-For when the request has none, so a value
 * the browser sent itself is indistinguishable from a real one. It can only
 * be trusted when `trustedHops` reverse proxies (e.g. an ingress) sit in
 * front of this server: each appends the address it saw, so the client is the
 * entry `trustedHops` places from the end. With no trusted proxy in front,
 * nothing is forwarded and the API records this server's address.
 */
export function clientAddress(forwardedFor: string | null, trustedHops: number): string | null {
  if (!forwardedFor || trustedHops < 1) return null;
  const chain = forwardedFor
    .split(",")
    .map((entry) => entry.trim())
    .filter(Boolean);
  return chain.length >= trustedHops ? chain[chain.length - trustedHops] : null;
}

/**
 * Headers for the upstream API call: a small allow-list from the browser
 * (never its cookies or Authorization), the session's bearer token, and the
 * client's address when it can be trusted.
 */
export function upstreamHeaders(
  incoming: Headers,
  accessToken: string | null,
  trustedHops: number,
): Headers {
  const headers = new Headers();
  for (const name of FORWARDED_REQUEST_HEADERS) {
    const value = incoming.get(name);
    if (value) headers.set(name, value);
  }
  if (accessToken) headers.set("authorization", `Bearer ${accessToken}`);
  const client = clientAddress(incoming.get("x-forwarded-for"), trustedHops);
  if (client) headers.set("x-forwarded-for", client);
  return headers;
}
