"use client";

import { zodResolver } from "@hookform/resolvers/zod";
import { createApiClient } from "@opspilot/api-client";
import type { components } from "@opspilot/api-client/schema";
import { useState } from "react";
import { useForm } from "react-hook-form";

import { Button } from "@/components/ui/button";
import { Field } from "@/components/ui/field";
import { Input, Select, Textarea } from "@/components/ui/input";
import { incidentSchema, type IncidentValues, serverFieldErrors } from "@/lib/form-schemas";
import { SEVERITIES } from "@/lib/incident-filters";

type Incident = components["schemas"]["IncidentOut"];
type ServiceOption = Pick<components["schemas"]["ServiceOut"], "id" | "name">;

const FIELDS = ["title", "severity", "service_id", "description"] as const;

export function IncidentForm({
  services,
  onCreated,
}: {
  services: ServiceOption[];
  onCreated: (incident: Incident) => void;
}) {
  const {
    register,
    handleSubmit,
    setError,
    formState: { errors, isSubmitting },
  } = useForm<IncidentValues>({
    resolver: zodResolver(incidentSchema),
    defaultValues: { title: "", severity: "medium", service_id: "", description: "" },
  });
  // One key per form instance: a double submit cannot open two incidents.
  const [idempotencyKey] = useState(() => crypto.randomUUID());

  async function submit(values: IncidentValues) {
    const { data, error } = await createApiClient(window.location.origin).POST("/api/v1/incidents", {
      params: { header: { "Idempotency-Key": idempotencyKey } },
      body: {
        title: values.title,
        severity: values.severity as Incident["severity"],
        service_id: values.service_id || null,
        description: values.description || null,
        source: "manual",
      },
    });
    if (data) return onCreated(data);
    const server = serverFieldErrors(error, FIELDS);
    for (const field of FIELDS) {
      const message = server.fields[field];
      if (message) setError(field, { message });
    }
    if (server.form || Object.keys(server.fields).length === 0) {
      setError("root", { message: server.form ?? "The incident could not be created. Please try again." });
    }
  }

  return (
    <form onSubmit={handleSubmit(submit)} noValidate className="grid gap-4 sm:grid-cols-2">
      <Field label="Title" error={errors.title?.message} className="sm:col-span-2">
        {(control) => (
          <Input
            {...control}
            {...register("title")}
            required
            maxLength={200}
            placeholder="Checkout error rate above 5%"
          />
        )}
      </Field>
      <Field label="Severity" error={errors.severity?.message}>
        {(control) => (
          <Select {...control} {...register("severity")}>
            {SEVERITIES.map((s) => (
              <option key={s} value={s}>
                {s[0].toUpperCase() + s.slice(1)}
              </option>
            ))}
          </Select>
        )}
      </Field>
      <Field label="Service" error={errors.service_id?.message}>
        {(control) => (
          <Select {...control} {...register("service_id")}>
            <option value="">Not yet known</option>
            {services.map((s) => (
              <option key={s.id} value={s.id}>
                {s.name}
              </option>
            ))}
          </Select>
        )}
      </Field>
      <Field label="Description" error={errors.description?.message} className="sm:col-span-2">
        {(control) => <Textarea {...control} {...register("description")} rows={3} maxLength={5000} />}
      </Field>
      {errors.root && (
        <p role="alert" className="text-sm text-critical sm:col-span-2">
          {errors.root.message}
        </p>
      )}
      <div className="flex justify-end sm:col-span-2">
        <Button type="submit" disabled={isSubmitting}>
          {isSubmitting ? "Creating…" : "Create incident"}
        </Button>
      </div>
    </form>
  );
}
