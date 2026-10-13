/**
 * Backend-for-frontend proxy to the OpsPilot API.
 *
 * The browser never sees an access token: this handler looks the session up,
 * refreshes the token if needed, and forwards the call with Authorization set.
 * The API address is read at request time.
 */
import { type NextRequest, NextResponse } from "next/server";

import { serverConfig } from "@/server/config";
import { upstreamHeaders } from "@/server/forwarding";
import { accessTokenFor } from "@/server/oidc";
import { isSameOrigin } from "@/server/request";
import { SESSION_COOKIE } from "@/server/sessions";

const DROPPED_RESPONSE_HEADERS = ["connection", "transfer-encoding", "content-encoding", "content-length"];

async function proxy(request: NextRequest, context: { params: Promise<{ path: string[] }> }) {
  if (!["GET", "HEAD"].includes(request.method) && !isSameOrigin(request)) {
    return NextResponse.json({ detail: "Forbidden" }, { status: 403 });
  }

  const { path } = await context.params;
  const target = new URL(`/api/v1/${path.map(encodeURIComponent).join("/")}`, serverConfig().apiUrl);
  target.search = request.nextUrl.search;

  const token = await accessTokenFor(request.cookies.get(SESSION_COOKIE)?.value);
  const headers = upstreamHeaders(request.headers, token, serverConfig().trustedProxyHops);

  let upstream: Response;
  try {
    upstream = await fetch(target, {
      method: request.method,
      headers,
      body: ["GET", "HEAD"].includes(request.method) ? undefined : await request.arrayBuffer(),
      redirect: "manual",
      cache: "no-store",
    });
  } catch {
    return NextResponse.json({ detail: "API unavailable" }, { status: 502 });
  }

  const responseHeaders = new Headers(upstream.headers);
  for (const name of DROPPED_RESPONSE_HEADERS) responseHeaders.delete(name);
  return new NextResponse(upstream.body, { status: upstream.status, headers: responseHeaders });
}

export { proxy as DELETE, proxy as GET, proxy as PATCH, proxy as POST, proxy as PUT };
