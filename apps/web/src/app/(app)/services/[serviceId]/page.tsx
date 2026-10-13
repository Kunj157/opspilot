import Link from "next/link";
import { Suspense } from "react";

import { ServiceDetail } from "@/components/services/service-detail";
import { can } from "@/server/permissions";

export const metadata = { title: "Service · OpsPilot" };

async function Detail() {
  return <ServiceDetail canManage={await can("manage_services")} />;
}

export default function ServicePage() {
  return (
    <main className="w-full max-w-5xl flex-1 px-4 py-10 sm:px-8 sm:py-12">
      <Link href="/services" className="font-mono text-xs uppercase tracking-[0.18em] text-accent hover:underline">
        ← Services
      </Link>
      <div className="mt-4">
        <Suspense fallback={<div className="h-64 animate-pulse rounded-card bg-surface-2" />}>
          <Detail />
        </Suspense>
      </div>
    </main>
  );
}
