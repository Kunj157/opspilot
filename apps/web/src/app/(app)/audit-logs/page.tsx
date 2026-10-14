import { Suspense } from "react";

import { AuditLogExplorer } from "@/components/audit/audit-log-explorer";
import { getCurrentUser } from "@/server/current-user";
import { PageHeader } from "@/components/ui/page-header";

export const metadata = { title: "Audit log · OpsPilot" };

async function AuditLogGate() {
  const { permissions } = await getCurrentUser();
  if (!permissions.includes("view_audit_logs")) {
    return (
      <p
        role="alert"
        className="rounded-card border border-border bg-surface-2 px-5 py-10 text-center text-sm text-fg-secondary shadow-3"
      >
        You don&apos;t have access to the audit log. It is available to incident commanders and
        administrators.
      </p>
    );
  }
  return <AuditLogExplorer />;
}

export default function AuditLogPage() {
  return (
    <main className="w-full max-w-6xl flex-1 px-4 py-10 sm:px-8 sm:py-12">
      <PageHeader
        eyebrow="Governance"
        title="Audit log"
        description="Every change made by people, agents, and the system in your organization. Records cannot be edited or deleted."
      />
      <div className="mt-10">
        <Suspense fallback={<div className="skeleton h-64 rounded-card" />}>
          <AuditLogGate />
        </Suspense>
      </div>
    </main>
  );
}
