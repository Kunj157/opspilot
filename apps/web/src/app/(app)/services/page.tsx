import { Suspense } from "react";

import { ServiceCatalog } from "@/components/services/service-catalog";
import { can } from "@/server/permissions";

export const metadata = { title: "Services · OpsPilot" };

async function Catalog() {
  return <ServiceCatalog canManage={await can("manage_services")} />;
}

export default function ServicesPage() {
  return (
    <main className="w-full max-w-5xl flex-1 px-4 py-10 sm:px-8 sm:py-12">
      <p className="font-mono text-xs uppercase tracking-[0.18em] text-accent">Catalog</p>
      <h1 className="mt-3 text-3xl font-semibold tracking-tight sm:text-4xl">Services</h1>
      <p className="mt-3 max-w-xl text-fg-secondary">
        Everything OpsPilot watches, with its owner and where it runs.
      </p>
      <div className="mt-10">
        <Suspense fallback={<div className="h-36 animate-pulse rounded-card bg-surface-2" />}>
          <Catalog />
        </Suspense>
      </div>
    </main>
  );
}
