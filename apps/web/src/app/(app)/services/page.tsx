import { Suspense } from "react";

import { ServiceCatalog } from "@/components/services/service-catalog";
import { can } from "@/server/permissions";
import { PageHeader } from "@/components/ui/page-header";

export const metadata = { title: "Services · OpsPilot" };

async function Catalog() {
  return <ServiceCatalog canManage={await can("manage_services")} />;
}

export default function ServicesPage() {
  return (
    <main className="w-full max-w-6xl flex-1 px-4 py-10 sm:px-8 sm:py-12">
      <PageHeader
        eyebrow="Catalog"
        title="Services"
        description="Everything OpsPilot watches, with its owner and where it runs."
      />
      <div className="mt-10">
        <Suspense fallback={<div className="skeleton h-36 rounded-card" />}>
          <Catalog />
        </Suspense>
      </div>
    </main>
  );
}
