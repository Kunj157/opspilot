import type { Permission } from "@opspilot/api-client";

import type { IconName } from "@/components/icons";

export type NavItem = { href: string; label: string; icon: IconName };

export const NAV_ITEMS: (NavItem & { permission?: Permission })[] = [
  { href: "/", label: "Command center", icon: "overview" },
  { href: "/incidents", label: "Incidents", icon: "incidents", permission: "view_incidents" },
  { href: "/services", label: "Services", icon: "services", permission: "view_services" },
  { href: "/runbooks", label: "Runbooks", icon: "runbooks", permission: "view_incidents" },
  { href: "/models", label: "ML detector", icon: "models", permission: "view_incidents" },
  { href: "/audit-logs", label: "Audit log", icon: "audit", permission: "view_audit_logs" },
  { href: "/status", label: "System status", icon: "status" },
];

export function isActive(href: string, pathname: string): boolean {
  return href === "/" ? pathname === "/" : pathname === href || pathname.startsWith(`${href}/`);
}
