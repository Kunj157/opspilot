import { Suspense } from "react";

import { ModelComparison } from "@/components/ml/model-comparison";
import { getCurrentUser } from "@/server/current-user";

export const metadata = { title: "ML detector · OpsPilot" };

async function Comparison() {
  const { permissions } = await getCurrentUser();
  return <ModelComparison canManage={permissions.includes("manage_models")} />;
}

export default function ModelsPage() {
  return (
    <main className="w-full max-w-5xl flex-1 px-4 py-10 sm:px-8 sm:py-12">
      <p className="font-mono text-xs uppercase tracking-[0.18em] text-accent">Detection</p>
      <h1 className="mt-3 text-3xl font-semibold tracking-tight sm:text-4xl">ML detector</h1>
      <p className="mt-3 max-w-xl text-fg-secondary">
        How the Isolation Forest compares with the statistical baseline on failure runs it never saw,
        and what it would have flagged while running in shadow mode.
      </p>
      <div className="mt-10">
        <Suspense fallback={<div className="h-64 animate-pulse rounded-card bg-surface-2" />}>
          <Comparison />
        </Suspense>
      </div>
    </main>
  );
}
