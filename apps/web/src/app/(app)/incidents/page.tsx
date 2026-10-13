import { Suspense } from "react";

import { IncidentList } from "@/components/incidents/incident-list";
import { getCurrentUser } from "@/server/current-user";

export const metadata = { title: "Incidents · OpsPilot" };

async function List() {
  const user = await getCurrentUser();
  return <IncidentList canManage={user.permissions.includes("manage_incidents")} currentUserId={user.id} />;
}

export default function IncidentsPage() {
  return (
    <main className="w-full max-w-6xl flex-1 px-4 py-10 sm:px-8 sm:py-12">
      <p className="font-mono text-xs uppercase tracking-[0.18em] text-accent">Response</p>
      <h1 className="mt-3 text-3xl font-semibold tracking-tight sm:text-4xl">Incidents</h1>
      <p className="mt-3 max-w-xl text-fg-secondary">
        Every incident in your organization, updated live as it moves through response.
      </p>
      <div className="mt-10">
        <Suspense fallback={<div className="h-96 animate-pulse rounded-card bg-surface-2" />}>
          <List />
        </Suspense>
      </div>
    </main>
  );
}
