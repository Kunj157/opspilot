"use client";

import { zodResolver } from "@hookform/resolvers/zod";
import { createApiClient } from "@opspilot/api-client";
import type { components } from "@opspilot/api-client/schema";
import { useId } from "react";
import { useForm } from "react-hook-form";

import { Button } from "@/components/ui/button";
import { Field } from "@/components/ui/field";
import { Textarea } from "@/components/ui/input";
import { runbookSchema, type RunbookValues } from "@/lib/form-schemas";

type Runbook = components["schemas"]["RunbookOut"];

export const TEMPLATE = `---
title: 
services: []
owner: 
version: 1
---

## Scope

## Symptoms

## Prerequisites

## Investigation steps

## Safe actions

## High-risk actions

## Verification

## Rollback

## Escalation
`;

function messageFor(status: number, error: unknown): string {
  const detail = (error as { detail?: unknown })?.detail;
  if (status === 409) return "A runbook with this title already exists.";
  if (status === 403) return "You don't have permission to change runbooks.";
  if (Array.isArray(detail) && typeof detail[0]?.msg === "string") return `Invalid runbook: ${detail[0].msg}`;
  return "The runbook could not be saved. Please try again.";
}

/** Create a runbook, or save a new version of an existing one. */
export function RunbookForm({ runbook, onSaved }: { runbook?: Runbook; onSaved: (runbook: Runbook) => void }) {
  const {
    register,
    handleSubmit,
    setError,
    formState: { errors, isSubmitting },
  } = useForm<RunbookValues>({
    resolver: zodResolver(runbookSchema),
    defaultValues: { content: runbook?.content ?? TEMPLATE },
  });

  async function submit({ content }: RunbookValues) {
    const api = createApiClient(window.location.origin);
    const result = runbook
      ? await api.PUT("/api/v1/runbooks/{runbook_id}", {
          params: { path: { runbook_id: runbook.id } },
          body: { content },
        })
      : await api.POST("/api/v1/runbooks", { body: { content } });
    if (result.data) onSaved(result.data);
    else setError("content", { message: messageFor(result.response.status, result.error) });
  }

  const error = errors.content?.message;
  const errorId = useId();
  return (
    <form onSubmit={handleSubmit(submit)} noValidate className="flex flex-col gap-4">
      <Field label="Runbook (markdown with front matter)">
        {(control) => (
          <Textarea
            {...control}
            {...register("content")}
            rows={18}
            spellCheck={false}
            aria-invalid={error ? true : undefined}
            aria-describedby={error ? errorId : undefined}
            className="font-mono text-xs leading-relaxed"
          />
        )}
      </Field>
      {error && (
        <p id={errorId} role="alert" className="text-sm text-critical">
          {error}
        </p>
      )}
      <div className="flex justify-end">
        <Button type="submit" disabled={isSubmitting}>
          {isSubmitting ? "Saving…" : runbook ? "Save new version" : "Create runbook"}
        </Button>
      </div>
    </form>
  );
}
