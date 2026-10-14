"use client";

import { zodResolver } from "@hookform/resolvers/zod";
import { createApiClient } from "@opspilot/api-client";
import type { components } from "@opspilot/api-client/schema";
import { useState } from "react";
import { useForm } from "react-hook-form";

import { Button } from "@/components/ui/button";
import { Field } from "@/components/ui/field";
import { Input } from "@/components/ui/input";
import { serverFieldErrors, serviceSchema, type ServiceValues } from "@/lib/form-schemas";

type Service = components["schemas"]["ServiceOut"];
type EditableField = keyof ServiceValues;

const FIELDS: { name: EditableField; label: string; required?: boolean; placeholder?: string }[] = [
  { name: "name", label: "Name", required: true, placeholder: "Checkout" },
  { name: "slug", label: "Slug", required: true, placeholder: "checkout" },
  { name: "description", label: "Description" },
  { name: "owner_team", label: "Owner team", placeholder: "payments" },
  { name: "repository_url", label: "Repository URL", placeholder: "https://github.com/…" },
  { name: "namespace", label: "Namespace", placeholder: "demo" },
  { name: "deployment_name", label: "Deployment", placeholder: "checkout" },
];
const NAMES = FIELDS.map((f) => f.name);

export function slugify(name: string): string {
  return name
    .toLowerCase()
    .replace(/[^a-z0-9]+/g, "-")
    .replace(/^-+|-+$/g, "")
    .slice(0, 63);
}

function initialValues(service?: Pick<Service, EditableField>): ServiceValues {
  return Object.fromEntries(NAMES.map((name) => [name, service?.[name] ?? ""])) as ServiceValues;
}

export function ServiceForm({
  service,
  onSaved,
}: {
  service?: Pick<Service, "id" | EditableField>;
  onSaved: (saved: Service) => void;
}) {
  const {
    register,
    handleSubmit,
    setValue,
    setError,
    getFieldState,
    formState: { errors, isSubmitting, dirtyFields },
  } = useForm<ServiceValues>({ resolver: zodResolver(serviceSchema), defaultValues: initialValues(service) });
  // One key per form instance: a double submit or retry cannot create two services.
  const [idempotencyKey] = useState(() => crypto.randomUUID());

  // The slug follows the name until someone edits the slug itself.
  const name = register("name", {
    onChange: (event) => {
      if (!service && !getFieldState("slug").isDirty) setValue("slug", slugify(event.target.value));
    },
  });

  async function submit(values: ServiceValues) {
    const api = createApiClient(window.location.origin);
    const changed = NAMES.filter((field) => (service ? dirtyFields[field] : values[field] !== ""));
    const body = Object.fromEntries(changed.map((field) => [field, values[field] === "" ? null : values[field]]));
    const result = service
      ? await api.PATCH("/api/v1/services/{service_id}", { params: { path: { service_id: service.id } }, body })
      : await api.POST("/api/v1/services", {
          params: { header: { "Idempotency-Key": idempotencyKey } },
          body: body as components["schemas"]["ServiceCreate"],
        });
    if (result.data) return onSaved(result.data as Service);

    if (result.response.status === 409)
      return setError("slug", { message: "A service with this slug already exists." });
    const server = serverFieldErrors(result.error, NAMES);
    for (const field of NAMES) {
      const message = server.fields[field];
      if (message) setError(field, { message });
    }
    if (server.form || Object.keys(server.fields).length === 0) {
      setError("root", { message: server.form ?? "The service could not be saved. Please try again." });
    }
  }

  return (
    <form onSubmit={handleSubmit(submit)} noValidate className="grid gap-4 sm:grid-cols-2">
      {FIELDS.map(({ name: field, label, required, placeholder }) => (
        <Field
          key={field}
          label={label}
          required={required}
          error={errors[field]?.message}
          className={field === "description" ? "sm:col-span-2" : undefined}
        >
          {(control) => (
            <Input {...control} {...(field === "name" ? name : register(field))} placeholder={placeholder} />
          )}
        </Field>
      ))}
      {errors.root && (
        <p role="alert" className="text-sm text-critical sm:col-span-2">
          {errors.root.message}
        </p>
      )}
      <div className="flex justify-end sm:col-span-2">
        <Button type="submit" disabled={isSubmitting}>
          {isSubmitting ? "Saving…" : service ? "Save changes" : "Create service"}
        </Button>
      </div>
    </form>
  );
}
