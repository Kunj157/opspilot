import "server-only";

import type { NextRequest } from "next/server";

import { serverConfig } from "./config";

export function isSecure(request: NextRequest): boolean {
  return (
    serverConfig().production ||
    request.nextUrl.protocol === "https:" ||
    request.headers.get("x-forwarded-proto") === "https"
  );
}

/**
 * CSRF guard for state-changing requests: the browser must say the request
 * came from this origin. SameSite=Lax cookies are the first line; this is the second.
 */
export function isSameOrigin(request: NextRequest): boolean {
  const origin = request.headers.get("origin");
  if (origin) return origin === request.nextUrl.origin;
  return request.headers.get("sec-fetch-site") === "same-origin";
}
