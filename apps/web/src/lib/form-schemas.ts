/**
 * Client-side validation for the incident, service, and runbook forms. The
 * rules mirror the API's request models, so most mistakes are explained before
 * a request is sent; the API remains the authority and its 422s still map onto
 * the same fields.
 */
import { z } from "zod";

import { SEVERITIES } from "./incident-filters";

const SLUG = /^[a-z0-9]+(-[a-z0-9]+)*$/;
const DNS_LABEL = /^[a-z0-9]([-a-z0-9]*[a-z0-9])?$/;
const DNS_SUBDOMAIN = /^[a-z0-9]([-a-z0-9.]*[a-z0-9])?$/;

/** An optional text field: blank is allowed and means "not set". */
const optional = (rule: z.ZodType<string, string>) => z.union([z.literal(""), rule]);

export const incidentSchema = z.object({
  title: z.string().trim().min(1, "Give the incident a title.").max(200, "Keep the title under 200 characters."),
  severity: z.enum(SEVERITIES as [string, ...string[]]),
  service_id: z.string(),
  description: z.string().trim().max(5000, "Keep the description under 5000 characters."),
});
export type IncidentValues = z.infer<typeof incidentSchema>;

const lowercase = "Use lowercase letters, numbers, and hyphens.";

export const serviceSchema = z.object({
  name: z.string().trim().min(1, "Give the service a name.").max(100, "Keep the name under 100 characters."),
  slug: z
    .string()
    .trim()
    .min(2, "Use at least 2 characters.")
    .max(63, "Use at most 63 characters.")
    .regex(SLUG, lowercase),
  description: optional(z.string().max(2000, "Keep the description under 2000 characters.")),
  owner_team: optional(z.string().max(100, "Keep the team under 100 characters.")),
  repository_url: optional(z.url({ protocol: /^https?$/, error: "Use an http(s) URL." })),
  namespace: optional(z.string().max(63, "Use at most 63 characters.").regex(DNS_LABEL, lowercase)),
  deployment_name: optional(
    z.string().max(253, "Use at most 253 characters.").regex(DNS_SUBDOMAIN, "Use lowercase letters, numbers, dots, and hyphens."),
  ),
});
export type ServiceValues = z.infer<typeof serviceSchema>;

export const runbookSchema = z.object({
  content: z
    .string()
    .refine((value) => value.trimStart().startsWith("---"), "Invalid runbook: start with front matter between --- lines (title, services, symptoms)."),
});
export type RunbookValues = z.infer<typeof runbookSchema>;

/** FastAPI 422 details → field messages, for the fields a form knows about. */
export function serverFieldErrors<F extends string>(
  body: unknown,
  fields: readonly F[],
): { fields: Partial<Record<F, string>>; form?: string } {
  const detail = (body as { detail?: unknown } | null)?.detail;
  if (!Array.isArray(detail)) return { fields: {} };
  const result: { fields: Partial<Record<F, string>>; form?: string } = { fields: {} };
  for (const item of detail as { loc: (string | number)[]; msg: string }[]) {
    const field = String(item.loc[item.loc.length - 1]) as F;
    if (fields.includes(field)) result.fields[field] = item.msg;
    else result.form = item.msg;
  }
  return result;
}
