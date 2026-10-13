"use client";

import { createApiClient } from "@opspilot/api-client";
import type { components } from "@opspilot/api-client/schema";
import { type FormEvent, useId, useState } from "react";

import { Button } from "@/components/ui/button";
import { SEVERITIES } from "@/lib/incident-filters";

type Incident = components["schemas"]["IncidentOut"];
type ServiceOption = Pick<components["schemas"]["ServiceOut"], "id" | "name">;
type Field = "title" | "severity" | "service_id" | "description";
type Errors = Partial<Record<Field | "form", string>>;

const inputClass =
  "w-full rounded-sm border border-border bg-surface-1 px-2.5 text-sm placeholder:text-fg-muted focus:border-accent focus:outline-none aria-[invalid=true]:border-critical";

function errorsFrom(body: unknown): Errors {
  const detail = (body as { detail?: unknown })?.detail;
  if (!Array.isArray(detail)) return { form: "The incident could not be created. Please try again." };
  const errors: Errors = {};
  for (const item of detail as { loc: (string | number)[]; msg: string }[]) {
    const field = String(item.loc[item.loc.length - 1]);
    if (["title", "severity", "service_id", "description"].includes(field)) errors[field as Field] = item.msg;
    else errors.form = item.msg;
  }
  return errors;
}

export function IncidentForm({
  services,
  onCreated,
}: {
  services: ServiceOption[];
  onCreated: (incident: Incident) => void;
}) {
  const id = useId();
  const [errors, setErrors] = useState<Errors>({});
  const [saving, setSaving] = useState(false);
  // One key per form instance: a double submit cannot open two incidents.
  const [idempotencyKey] = useState(() => crypto.randomUUID());

  async function submit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    const form = new FormData(event.currentTarget);
    const title = String(form.get("title") ?? "").trim();
    if (!title) {
      setErrors({ title: "Give the incident a title." });
      return;
    }
    setSaving(true);
    setErrors({});
    const description = String(form.get("description") ?? "").trim();
    const serviceId = String(form.get("service_id") ?? "");
    const { data, error } = await createApiClient(window.location.origin).POST("/api/v1/incidents", {
      params: { header: { "Idempotency-Key": idempotencyKey } },
      body: {
        title,
        severity: form.get("severity") as Incident["severity"],
        service_id: serviceId || null,
        description: description || null,
        source: "manual",
      },
    });
    setSaving(false);
    if (data) onCreated(data);
    else setErrors(errorsFrom(error));
  }

  const describe = (field: Field) =>
    errors[field] ? { "aria-invalid": true, "aria-describedby": `${id}-${field}-error` } : {};
  const message = (field: Field) =>
    errors[field] && (
      <p id={`${id}-${field}-error`} className="mt-1 text-xs text-critical">
        {errors[field]}
      </p>
    );

  return (
    <form onSubmit={submit} noValidate className="grid gap-4 sm:grid-cols-2">
      <div className="sm:col-span-2">
        <label htmlFor={`${id}-title`} className="mb-1.5 block text-xs text-fg-secondary">
          Title
        </label>
        <input
          id={`${id}-title`}
          name="title"
          required
          maxLength={200}
          placeholder="Checkout error rate above 5%"
          className={`h-9 ${inputClass}`}
          {...describe("title")}
        />
        {message("title")}
      </div>
      <div>
        <label htmlFor={`${id}-severity`} className="mb-1.5 block text-xs text-fg-secondary">
          Severity
        </label>
        <select id={`${id}-severity`} name="severity" defaultValue="medium" className={`h-9 ${inputClass}`} {...describe("severity")}>
          {SEVERITIES.map((s) => (
            <option key={s} value={s}>
              {s[0].toUpperCase() + s.slice(1)}
            </option>
          ))}
        </select>
        {message("severity")}
      </div>
      <div>
        <label htmlFor={`${id}-service`} className="mb-1.5 block text-xs text-fg-secondary">
          Service
        </label>
        <select id={`${id}-service`} name="service_id" defaultValue="" className={`h-9 ${inputClass}`} {...describe("service_id")}>
          <option value="">Not yet known</option>
          {services.map((s) => (
            <option key={s.id} value={s.id}>
              {s.name}
            </option>
          ))}
        </select>
        {message("service_id")}
      </div>
      <div className="sm:col-span-2">
        <label htmlFor={`${id}-description`} className="mb-1.5 block text-xs text-fg-secondary">
          Description
        </label>
        <textarea
          id={`${id}-description`}
          name="description"
          rows={3}
          maxLength={5000}
          className={`py-2 ${inputClass}`}
          {...describe("description")}
        />
        {message("description")}
      </div>
      {errors.form && (
        <p role="alert" className="text-sm text-critical sm:col-span-2">
          {errors.form}
        </p>
      )}
      <div className="flex justify-end sm:col-span-2">
        <Button type="submit" disabled={saving}>
          {saving ? "Creating…" : "Create incident"}
        </Button>
      </div>
    </form>
  );
}
