"use client";

import { createApiClient } from "@opspilot/api-client";
import type { components } from "@opspilot/api-client/schema";
import { type FormEvent, useId, useState } from "react";

type Service = components["schemas"]["ServiceOut"];
type EditableField =
  | "name"
  | "slug"
  | "description"
  | "owner_team"
  | "repository_url"
  | "namespace"
  | "deployment_name";
type Values = Record<EditableField, string>;
type Errors = Partial<Record<EditableField | "form", string>>;

const FIELDS: { name: EditableField; label: string; required?: boolean; placeholder?: string }[] = [
  { name: "name", label: "Name", required: true, placeholder: "Checkout" },
  { name: "slug", label: "Slug", required: true, placeholder: "checkout" },
  { name: "description", label: "Description" },
  { name: "owner_team", label: "Owner team", placeholder: "payments" },
  { name: "repository_url", label: "Repository URL", placeholder: "https://github.com/…" },
  { name: "namespace", label: "Namespace", placeholder: "demo" },
  { name: "deployment_name", label: "Deployment", placeholder: "checkout" },
];

export function slugify(name: string): string {
  return name
    .toLowerCase()
    .replace(/[^a-z0-9]+/g, "-")
    .replace(/^-+|-+$/g, "")
    .slice(0, 63);
}

function initialValues(service?: Pick<Service, EditableField>): Values {
  return Object.fromEntries(
    FIELDS.map(({ name }) => [name, service?.[name] ?? ""]),
  ) as Values;
}

type ValidationItem = { loc: (string | number)[]; msg: string };

function errorsFrom(status: number, body: unknown): Errors {
  if (status === 409) return { slug: "A service with this slug already exists." };
  const detail = (body as { detail?: unknown })?.detail;
  if (status === 422 && Array.isArray(detail)) {
    const errors: Errors = {};
    for (const item of detail as ValidationItem[]) {
      const field = item.loc[item.loc.length - 1];
      if (FIELDS.some((f) => f.name === field)) errors[field as EditableField] = item.msg;
      else errors.form = item.msg;
    }
    return errors;
  }
  return { form: "The service could not be saved. Please try again." };
}

export function ServiceForm({
  service,
  onSaved,
}: {
  service?: Pick<Service, "id" | EditableField>;
  onSaved: (saved: Service) => void;
}) {
  const formId = useId();
  const [values, setValues] = useState<Values>(() => initialValues(service));
  const [slugEdited, setSlugEdited] = useState(Boolean(service));
  const [errors, setErrors] = useState<Errors>({});
  const [saving, setSaving] = useState(false);
  // One key per form instance: a double submit or retry cannot create two services.
  const [idempotencyKey] = useState(() => crypto.randomUUID());

  function update(name: EditableField, value: string) {
    setValues((current) => {
      const next = { ...current, [name]: value };
      if (name === "name" && !slugEdited) next.slug = slugify(value);
      return next;
    });
    if (name === "slug") setSlugEdited(true);
  }

  async function submit(event: FormEvent) {
    event.preventDefault();
    setSaving(true);
    setErrors({});
    const api = createApiClient(window.location.origin);
    const original = initialValues(service);
    const changed = FIELDS.map((f) => f.name).filter((name) =>
      service ? values[name] !== original[name] : values[name] !== "",
    );
    const body = Object.fromEntries(
      changed.map((name) => [name, values[name] === "" ? null : values[name]]),
    );

    const result = service
      ? await api.PATCH("/api/v1/services/{service_id}", {
          params: { path: { service_id: service.id } },
          body,
        })
      : await api.POST("/api/v1/services", {
          params: { header: { "Idempotency-Key": idempotencyKey } },
          body: body as components["schemas"]["ServiceCreate"],
        });
    setSaving(false);
    if (result.data) onSaved(result.data as Service);
    else setErrors(errorsFrom(result.response.status, result.error));
  }

  return (
    <form onSubmit={submit} noValidate className="grid gap-4 sm:grid-cols-2">
      {FIELDS.map(({ name, label, required, placeholder }) => {
        const id = `${formId}-${name}`;
        const error = errors[name];
        return (
          <div key={name} className={name === "description" ? "sm:col-span-2" : undefined}>
            <div className="mb-1.5 flex gap-1 text-xs text-fg-secondary">
              <label htmlFor={id}>{label}</label>
              {/* Visual hint only; the input's required attribute is what assistive tech reads. */}
              {required && (
                <span aria-hidden className="text-accent">
                  *
                </span>
              )}
            </div>
            <input
              id={id}
              name={name}
              value={values[name]}
              required={required}
              placeholder={placeholder}
              onChange={(e) => update(name, e.target.value)}
              aria-invalid={error ? true : undefined}
              aria-describedby={error ? `${id}-error` : undefined}
              className="h-9 w-full rounded-sm border border-border bg-surface-1 px-2.5 text-sm placeholder:text-fg-muted focus:border-accent focus:outline-none aria-[invalid=true]:border-critical"
            />
            {error && (
              <p id={`${id}-error`} className="mt-1 text-xs text-critical">
                {error}
              </p>
            )}
          </div>
        );
      })}
      {errors.form && (
        <p role="alert" className="text-sm text-critical sm:col-span-2">
          {errors.form}
        </p>
      )}
      <div className="flex justify-end sm:col-span-2">
        <button
          type="submit"
          disabled={saving}
          className="rounded-sm bg-accent px-4 py-2 text-sm font-semibold text-on-accent hover:bg-accent-hover disabled:opacity-50"
        >
          {saving ? "Saving…" : service ? "Save changes" : "Create service"}
        </button>
      </div>
    </form>
  );
}
