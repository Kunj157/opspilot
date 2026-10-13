import "server-only";

import { createHash, randomBytes } from "node:crypto";

import { redis } from "./redis";

export { SESSION_COOKIE } from "./session-cookie";

export type Session = {
  subject: string;
  accessToken: string;
  refreshToken: string | null;
  idToken: string | null;
  /** epoch seconds */
  accessTokenExpiresAt: number;
  /** epoch seconds */
  sessionExpiresAt: number;
};

/** Redis keys use a hash of the session ID, so a Redis dump does not yield usable cookies. */
function key(sessionId: string) {
  return `opspilot:session:${createHash("sha256").update(sessionId).digest("hex")}`;
}

function ttl(session: Session) {
  return Math.max(1, session.sessionExpiresAt - Math.floor(Date.now() / 1000));
}

export async function createSession(session: Session): Promise<string> {
  const sessionId = randomBytes(32).toString("base64url");
  await (await redis()).set(key(sessionId), JSON.stringify(session), { EX: ttl(session) });
  return sessionId;
}

export async function readSession(sessionId: string | undefined): Promise<Session | null> {
  if (!sessionId) return null;
  const raw = await (await redis()).get(key(sessionId));
  return raw ? (JSON.parse(raw) as Session) : null;
}

export async function updateSession(sessionId: string, session: Session): Promise<void> {
  await (await redis()).set(key(sessionId), JSON.stringify(session), { EX: ttl(session) });
}

export async function deleteSession(sessionId: string | undefined): Promise<void> {
  if (sessionId) await (await redis()).del(key(sessionId));
}

export function sessionCookieOptions(secure: boolean, maxAge: number) {
  return { httpOnly: true, secure, sameSite: "lax" as const, path: "/", maxAge };
}
