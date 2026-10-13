import { type NextRequest, NextResponse } from "next/server";

import { SESSION_COOKIE } from "@/server/session-cookie";

/**
 * Optimistic check only: no session cookie means "go and sign in". The real
 * validation happens on the server when the session is read.
 */
export function proxy(request: NextRequest) {
  if (request.cookies.has(SESSION_COOKIE)) return NextResponse.next();
  const login = new URL("/login", request.nextUrl.origin);
  login.searchParams.set("returnTo", `${request.nextUrl.pathname}${request.nextUrl.search}`);
  return NextResponse.redirect(login);
}

export const config = {
  // Everything except the login page, auth routes, the API proxy, and static assets.
  matcher: ["/((?!login|auth/|api/|_next/|favicon.ico).*)"],
};
