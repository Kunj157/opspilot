"use client";

import dynamic from "next/dynamic";

/**
 * The create/edit forms only appear inside dialogs, so they (and react-hook-form
 * and zod with them) load when a dialog first opens, not with the page.
 */
function FormSkeleton() {
  return <div aria-hidden className="skeleton h-48 rounded-sm" />;
}

export const IncidentForm = dynamic(() => import("@/components/incidents/incident-form").then((m) => m.IncidentForm), {
  ssr: false,
  loading: FormSkeleton,
});

export const ServiceForm = dynamic(() => import("@/components/services/service-form").then((m) => m.ServiceForm), {
  ssr: false,
  loading: FormSkeleton,
});

export const RunbookForm = dynamic(() => import("@/components/runbooks/runbook-form").then((m) => m.RunbookForm), {
  ssr: false,
  loading: FormSkeleton,
});
