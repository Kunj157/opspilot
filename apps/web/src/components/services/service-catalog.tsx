"use client";

import { createApiClient } from "@opspilot/api-client";
import { useQuery, useQueryClient } from "@tanstack/react-query";
import Link from "next/link";
import { useState } from "react";

import { GlowEffect } from "@/components/motion/glow-effect";
import { InView } from "@/components/motion/in-view";
import { MotionScope } from "@/components/motion/motion-provider";
import { Button } from "@/components/ui/button";
import { Card } from "@/components/ui/card";
import { Modal } from "@/components/ui/modal";
import { useToast } from "@/components/ui/toast";

import { HealthBadge } from "./health-badge";
import { ServiceForm } from "./service-form";

export const SERVICES_KEY = ["services"] as const;

export function ServiceCatalog({ canManage }: { canManage: boolean }) {
  const [creating, setCreating] = useState(false);
  const queryClient = useQueryClient();
  const toast = useToast();
  const services = useQuery({
    queryKey: SERVICES_KEY,
    queryFn: async ({ signal }) => {
      const { data } = await createApiClient(window.location.origin).GET("/api/v1/services", { signal });
      if (!data) throw new Error("services unavailable");
      return data.items;
    },
  });

  return (
    <>
      {canManage && (
        <div className="mb-6 flex justify-end">
          <Button
            onClick={() => setCreating(true)}
          >
            New service
          </Button>
        </div>
      )}

      {services.isPending && (
        <div aria-hidden className="grid gap-4 sm:grid-cols-2 lg:grid-cols-3">
          {[0, 1, 2].map((i) => (
            <div key={i} className="h-36 skeleton rounded-card" />
          ))}
        </div>
      )}
      {services.isError && (
        <p role="alert" className="rounded-card border border-border bg-surface-2 p-5 text-sm text-critical">
          Services could not be loaded.
        </p>
      )}
      {services.isSuccess && services.data.length === 0 && (
        <p className="rounded-card border border-dashed border-border-strong p-10 text-center text-sm text-fg-muted">
          No services yet.{canManage ? " Add the first one to start tracking its health." : ""}
        </p>
      )}
      {services.isSuccess && services.data.length > 0 && (
        <MotionScope>
          <ul aria-label="Services" className="grid grid-cols-1 gap-4 sm:grid-cols-2 lg:grid-cols-3">
            {services.data.map((service, index) => (
              <li key={service.id}>
                <InView index={index} className="relative h-full">
                  {service.health_status === "critical" && <GlowEffect tone="critical" className="rounded-card" />}
                  <Card
                    as={Link}
                    tilt
                    href={`/services/${service.id}`}
                    className="group block h-full p-5 hover:border-border-strong"
                  >
                    <div className="flex items-start justify-between gap-3">
                      <div className="min-w-0">
                        <p className="truncate font-medium group-hover:text-accent">{service.name}</p>
                        <p className="truncate font-mono text-xs text-fg-muted">{service.slug}</p>
                      </div>
                      <HealthBadge health={service.health_status} />
                    </div>
                    {service.description && (
                      <p className="mt-3 line-clamp-2 text-sm text-fg-secondary">{service.description}</p>
                    )}
                    <p className="mt-4 truncate text-xs text-fg-muted">
                      {[service.owner_team, service.namespace && `ns/${service.namespace}`]
                        .filter(Boolean)
                        .join(" · ") || "No owner or namespace yet"}
                    </p>
                  </Card>
                </InView>
              </li>
            ))}
          </ul>
        </MotionScope>
      )}

      <Modal open={creating} title="New service" onClose={() => setCreating(false)}>
        <ServiceForm
          onSaved={(service) => {
            setCreating(false);
            toast(`Service “${service.name}” created`);
            void queryClient.invalidateQueries({ queryKey: SERVICES_KEY });
          }}
        />
      </Modal>
    </>
  );
}
