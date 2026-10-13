import * as client from "openid-client";
import { type NextRequest, NextResponse } from "next/server";

import { AUTH_FLOW_COOKIE } from "@/server/auth-flow";
import { oidc } from "@/server/oidc";
import { safeReturnTo } from "@/server/redirects";
import { isSecure } from "@/server/request";


export async function GET(request: NextRequest) {
  const config = await oidc();
  const codeVerifier = client.randomPKCECodeVerifier();
  const state = client.randomState();
  const nonce = client.randomNonce();
  const returnTo = safeReturnTo(request.nextUrl.searchParams.get("returnTo"));

  const authorizationUrl = client.buildAuthorizationUrl(config, {
    redirect_uri: new URL("/auth/callback", request.nextUrl.origin).toString(),
    scope: "openid profile email",
    code_challenge: await client.calculatePKCECodeChallenge(codeVerifier),
    code_challenge_method: "S256",
    state,
    nonce,
  });

  const response = NextResponse.redirect(authorizationUrl);
  response.cookies.set(
    AUTH_FLOW_COOKIE,
    Buffer.from(JSON.stringify({ codeVerifier, state, nonce, returnTo })).toString("base64url"),
    { httpOnly: true, secure: isSecure(request), sameSite: "lax", path: "/auth", maxAge: 600 },
  );
  return response;
}
