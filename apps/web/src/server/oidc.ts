import "server-only";

import * as client from "openid-client";

import { serverConfig } from "./config";
import { type Session, readSession, updateSession } from "./sessions";

let configuration: Promise<client.Configuration> | undefined;

export function oidc(): Promise<client.Configuration> {
  configuration ??= (async () => {
    const config = serverConfig();
    const issuer = new URL(config.oidcIssuer);
    // Plain HTTP is only tolerated for a local identity provider outside production.
    const insecure = issuer.protocol === "http:" && !config.production;
    return client.discovery(
      issuer,
      config.oidcClientId,
      config.oidcClientSecret,
      undefined,
      insecure ? { execute: [client.allowInsecureRequests] } : undefined,
    );
  })().catch((err: unknown) => {
    configuration = undefined; // retry discovery on the next request
    throw err;
  });
  return configuration;
}

const nowSeconds = () => Math.floor(Date.now() / 1000);

export function sessionFromTokens(
  tokens: client.TokenEndpointResponse & client.TokenEndpointResponseHelpers,
  previous?: Session,
): Session {
  const refreshExpiresIn = Number(tokens.refresh_expires_in ?? 0);
  return {
    subject: tokens.claims()?.sub ?? previous?.subject ?? "",
    accessToken: tokens.access_token,
    refreshToken: tokens.refresh_token ?? previous?.refreshToken ?? null,
    idToken: tokens.id_token ?? previous?.idToken ?? null,
    accessTokenExpiresAt: nowSeconds() + (tokens.expiresIn() ?? 60),
    sessionExpiresAt:
      refreshExpiresIn > 0 ? nowSeconds() + refreshExpiresIn : (previous?.sessionExpiresAt ?? nowSeconds() + 8 * 3600),
  };
}

/**
 * A valid access token for the session, refreshed when it is about to expire.
 * Returns null when the session is gone or can no longer be refreshed.
 */
export async function accessTokenFor(sessionId: string | undefined): Promise<string | null> {
  const session = await readSession(sessionId);
  if (!session || !sessionId) return null;
  if (session.accessTokenExpiresAt - 30 > nowSeconds()) return session.accessToken;
  if (!session.refreshToken) return null;
  try {
    const tokens = await client.refreshTokenGrant(await oidc(), session.refreshToken);
    const refreshed = sessionFromTokens(tokens, session);
    await updateSession(sessionId, refreshed);
    return refreshed.accessToken;
  } catch {
    return null;
  }
}
