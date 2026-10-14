import { Suspense } from "react";

import { EvaluationDashboard } from "@/components/evaluations/evaluation-dashboard";
import { PageHeader } from "@/components/ui/page-header";

export const metadata = { title: "Evaluations · OpsPilot" };

export default function EvaluationsPage() {
  return (
    <main className="w-full max-w-6xl flex-1 px-4 py-10 sm:px-8 sm:py-12">
      <PageHeader
        eyebrow="Quality"
        title="Evaluations"
        description="How well detection, the investigating agents, and remediation performed, computed from what actually happened."
      />
      <div className="mt-10">
        <Suspense fallback={<div className="skeleton h-96 rounded-card" />}>
          <EvaluationDashboard />
        </Suspense>
      </div>
    </main>
  );
}
