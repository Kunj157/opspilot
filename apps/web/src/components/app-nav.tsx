import type { Permission } from "@opspilot/api-client";

import { getCurrentUser } from "@/server/current-user";

import { NavLinks } from "./nav-links";

const ITEMS: { href: string; label: string; permission?: Permission }[] = [
  { href: "/", label: "Status" },
  { href: "/audit-logs", label: "Audit log", permission: "view_audit_logs" },
];

/** Navigation filtered by the user's permissions; the API enforces them regardless. */
export async function AppNav() {
  const { permissions } = await getCurrentUser();
  const visible = ITEMS.filter((item) => !item.permission || permissions.includes(item.permission));
  return <NavLinks items={visible.map(({ href, label }) => ({ href, label }))} />;
}

export function AppNavSkeleton() {
  return <div aria-hidden className="h-8 w-40 animate-pulse rounded-card bg-surface-3" />;
}
