import * as client from "openid-client";
import { type NextRequest, NextResponse } from "next/server";

import { AUTH_FLOW_COOKIE } from "@/server/auth-flow";
import { oidc, sessionFromTokens } from "@/server/oidc";
import { safeReturnTo } from "@/server/redirects";
import { isSecure } from "@/server/request";
import { SESSION_COOKIE, createSession, sessionCookieOptions } from "@/server/sessions";

type AuthFlow = { codeVerifier: string; state: string; nonce: string; returnTo: string };

function loginError(request: NextRequest) {
  const response = NextResponse.redirect(new URL("/login?error=callback", request.nextUrl.origin));
  response.cookies.delete({ name: AUTH_FLOW_COOKIE, path: "/auth" });
  return response;
}

export async function GET(request: NextRequest) {
  const raw = request.cookies.get(AUTH_FLOW_COOKIE)?.value;
  if (!raw) return loginError(request);

  let flow: AuthFlow;
  try {
    flow = JSON.parse(Buffer.from(raw, "base64url").toString()) as AuthFlow;
  } catch {
    return loginError(request);
  }

  try {
    const tokens = await client.authorizationCodeGrant(await oidc(), new URL(request.url), {
      pkceCodeVerifier: flow.codeVerifier,
      expectedState: flow.state,
      expectedNonce: flow.nonce,
      idTokenExpected: true,
    });
    const session = sessionFromTokens(tokens);
    const sessionId = await createSession(session);

    const response = NextResponse.redirect(
      new URL(safeReturnTo(flow.returnTo), request.nextUrl.origin),
    );
    response.cookies.set(
      SESSION_COOKIE,
      sessionId,
      sessionCookieOptions(isSecure(request), session.sessionExpiresAt - Math.floor(Date.now() / 1000)),
    );
    response.cookies.delete({ name: AUTH_FLOW_COOKIE, path: "/auth" });
    return response;
  } catch (err) {
    console.error("login callback failed", err instanceof Error ? err.name : "unknown");
    return loginError(request);
  }
}
