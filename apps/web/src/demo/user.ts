import type { Me } from "@opspilot/api-client";

const id = (n: number) => `00000000-0000-4000-8000-${String(n).padStart(12, "0")}`;

/** The signed-in user of the static demo (NEXT_PUBLIC_DEMO=1): an incident commander with every permission. */
export const DEMO_USER: Me = {
  id: id(9001),
  email: "commander@demo.opspilot",
  display_name: "Demo Commander",
  organization: { id: id(9100), slug: "demo-shop" },
  roles: ["incident-commander"],
  permissions: [
    "view_services",
    "view_incidents",
    "manage_incidents",
    "start_investigation",
    "approve_remediation",
    "manage_services",
    "manage_runbooks",
    "view_audit_logs",
    "manage_users",
    "manage_models",
  ],
};
