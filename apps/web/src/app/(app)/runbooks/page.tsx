import { Suspense } from "react";

import { RunbookLibrary } from "@/components/runbooks/runbook-library";
import { can } from "@/server/permissions";
import { PageHeader } from "@/components/ui/page-header";

export const metadata = { title: "Runbooks · OpsPilot" };

async function Library() {
  return <RunbookLibrary canManage={await can("manage_runbooks")} />;
}

export default function RunbooksPage() {
  return (
    <main className="w-full max-w-6xl flex-1 px-4 py-10 sm:px-8 sm:py-12">
      <PageHeader
        eyebrow="Knowledge"
        title="Runbooks"
        description="Operational procedures, searchable by symptoms. Agents cite them; they never obey them."
      />
      <div className="mt-10">
        <Suspense fallback={<div className="skeleton h-40 rounded-card" />}>
          <Library />
        </Suspense>
      </div>
    </main>
  );
}
