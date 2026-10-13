import "server-only";

import type { Permission } from "@opspilot/api-client";

import { getCurrentUser } from "./current-user";

export async function can(permission: Permission): Promise<boolean> {
  return (await getCurrentUser()).permissions.includes(permission);
}
