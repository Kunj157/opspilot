import Link from "next/link";
import { Suspense } from "react";

import { RunbookDetail } from "@/components/runbooks/runbook-detail";
import { can } from "@/server/permissions";

export const metadata = { title: "Runbook · OpsPilot" };

async function Detail() {
  return <RunbookDetail canManage={await can("manage_runbooks")} />;
}

export default function RunbookPage() {
  return (
    <main className="w-full max-w-3xl flex-1 px-4 py-10 sm:px-8 sm:py-12">
      <Link href="/runbooks" className="font-mono text-xs uppercase tracking-[0.18em] text-accent hover:underline">
        ← Runbooks
      </Link>
      <div className="mt-4">
        <Suspense fallback={<div className="h-64 animate-pulse rounded-card bg-surface-2" />}>
          <Detail />
        </Suspense>
      </div>
    </main>
  );
}
