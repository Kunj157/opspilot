import "server-only";

import { cookies } from "next/headers";
import { redirect } from "next/navigation";

import { createApiClient, type Me } from "@opspilot/api-client";

import { serverConfig } from "./config";
import { accessTokenFor } from "./oidc";
import { SESSION_COOKIE } from "./sessions";

export type CurrentUser = Pick<Me, "display_name" | "email" | "organization" | "roles" | "permissions">;

/**
 * Data access layer for "who is signed in". Redirects to the login page when
 * there is no valid session. Returns only what the UI needs.
 */
export async function getCurrentUser(): Promise<CurrentUser> {
  const sessionId = (await cookies()).get(SESSION_COOKIE)?.value;
  const token = await accessTokenFor(sessionId);
  if (!token) redirect("/login");

  const api = createApiClient(serverConfig().apiUrl);
  const { data, response } = await api.GET("/api/v1/me", {
    headers: { Authorization: `Bearer ${token}` },
    cache: "no-store",
  });
  if (response.status === 401) redirect("/login");
  if (!data) throw new Error(`could not load the current user (HTTP ${response.status})`);
  const { display_name, email, organization, roles, permissions } = data;
  return { display_name, email, organization, roles, permissions };
}
