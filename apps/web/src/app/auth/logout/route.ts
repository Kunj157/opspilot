import * as client from "openid-client";
import { type NextRequest, NextResponse } from "next/server";

import { oidc } from "@/server/oidc";
import { isSameOrigin } from "@/server/request";
import { SESSION_COOKIE, deleteSession, readSession } from "@/server/sessions";

export async function POST(request: NextRequest) {
  if (!isSameOrigin(request)) {
    return NextResponse.json({ detail: "Forbidden" }, { status: 403 });
  }
  const sessionId = request.cookies.get(SESSION_COOKIE)?.value;
  const session = await readSession(sessionId);
  await deleteSession(sessionId);

  const signedOut = new URL("/login?signed_out=1", request.nextUrl.origin);
  let destination = signedOut;
  if (session?.idToken) {
    destination = client.buildEndSessionUrl(await oidc(), {
      id_token_hint: session.idToken,
      post_logout_redirect_uri: signedOut.toString(),
    });
  }
  // 303 turns the POST into a GET at the identity provider.
  const response = NextResponse.redirect(destination, 303);
  response.cookies.delete({ name: SESSION_COOKIE, path: "/" });
  return response;
}
