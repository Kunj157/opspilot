import { Suspense } from "react";

import { ModelComparison } from "@/components/ml/model-comparison";
import { getCurrentUser } from "@/server/current-user";
import { PageHeader } from "@/components/ui/page-header";

export const metadata = { title: "ML detector · OpsPilot" };

async function Comparison() {
  const { permissions } = await getCurrentUser();
  return <ModelComparison canManage={permissions.includes("manage_models")} />;
}

export default function ModelsPage() {
  return (
    <main className="w-full max-w-6xl flex-1 px-4 py-10 sm:px-8 sm:py-12">
      <PageHeader
        eyebrow="Detection"
        title="ML detector"
        description="How the Isolation Forest compares with the statistical baseline on failure runs it never saw, and what it would have flagged while running in shadow mode."
      />
      <div className="mt-10">
        <Suspense fallback={<div className="skeleton h-64 rounded-card" />}>
          <Comparison />
        </Suspense>
      </div>
    </main>
  );
}
