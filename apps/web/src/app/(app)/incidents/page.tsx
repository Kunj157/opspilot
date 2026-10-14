import { Suspense } from "react";

import { IncidentList } from "@/components/incidents/incident-list";
import { PageHeader } from "@/components/ui/page-header";
import { getCurrentUser } from "@/server/current-user";

export const metadata = { title: "Incidents · OpsPilot" };

async function List() {
  const user = await getCurrentUser();
  return <IncidentList canManage={user.permissions.includes("manage_incidents")} currentUserId={user.id} />;
}

export default function IncidentsPage() {
  return (
    <main className="w-full max-w-6xl flex-1 px-4 py-10 sm:px-8 sm:py-12">
      <PageHeader
        eyebrow="Response"
        title="Incidents"
        description="Every incident in your organization, updated live as it moves through response."
      />
      <div className="mt-10">
        <Suspense fallback={<div className="skeleton h-96 rounded-card" />}>
          <List />
        </Suspense>
      </div>
    </main>
  );
}
