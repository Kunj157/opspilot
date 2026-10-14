import { Suspense } from "react";

import { RunbookLibrary } from "@/components/runbooks/runbook-library";
import { can } from "@/server/permissions";

export const metadata = { title: "Runbooks · OpsPilot" };

async function Library() {
  return <RunbookLibrary canManage={await can("manage_runbooks")} />;
}

export default function RunbooksPage() {
  return (
    <main className="w-full max-w-5xl flex-1 px-4 py-10 sm:px-8 sm:py-12">
      <p className="font-mono text-xs uppercase tracking-[0.18em] text-accent">Knowledge</p>
      <h1 className="mt-3 text-3xl font-semibold tracking-tight sm:text-4xl">Runbooks</h1>
      <p className="mt-3 max-w-xl text-fg-secondary">
        Operational procedures, searchable by symptoms. Agents cite them; they never obey them.
      </p>
      <div className="mt-10">
        <Suspense fallback={<div className="h-40 animate-pulse rounded-card bg-surface-2" />}>
          <Library />
        </Suspense>
      </div>
    </main>
  );
}
