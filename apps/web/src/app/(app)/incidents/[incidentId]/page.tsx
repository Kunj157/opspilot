import Link from "next/link";
import { Suspense } from "react";

import { IncidentDetail } from "@/components/incidents/incident-detail";
import { getCurrentUser } from "@/server/current-user";

export const metadata = { title: "Incident · OpsPilot" };

async function Detail() {
  const { permissions } = await getCurrentUser();
  return (
    <IncidentDetail
      permissions={{
        manage: permissions.includes("manage_incidents"),
        investigate: permissions.includes("start_investigation"),
        approve: permissions.includes("approve_remediation"),
      }}
    />
  );
}

export default function IncidentPage() {
  return (
    <main className="w-full max-w-6xl flex-1 px-4 py-10 sm:px-8 sm:py-12">
      <Link href="/incidents" className="font-mono text-xs uppercase tracking-[0.18em] text-accent hover:underline">
        ← Incidents
      </Link>
      <div className="mt-4">
        <Suspense fallback={<div className="skeleton h-96 rounded-card" />}>
          <Detail />
        </Suspense>
      </div>
    </main>
  );
}
