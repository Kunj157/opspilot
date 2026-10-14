"use client";

import { createApiClient } from "@opspilot/api-client";
import type { components } from "@opspilot/api-client/schema";
import { type FormEvent, useId, useState } from "react";

import { Button } from "@/components/ui/button";
import { Textarea } from "@/components/ui/input";

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
  const id = useId();
  const [content, setContent] = useState(runbook?.content ?? TEMPLATE);
  const [error, setError] = useState<string | null>(null);
  const [saving, setSaving] = useState(false);

  async function submit(event: FormEvent) {
    event.preventDefault();
    setSaving(true);
    setError(null);
    const api = createApiClient(window.location.origin);
    const result = runbook
      ? await api.PUT("/api/v1/runbooks/{runbook_id}", {
          params: { path: { runbook_id: runbook.id } },
          body: { content },
        })
      : await api.POST("/api/v1/runbooks", { body: { content } });
    setSaving(false);
    if (result.data) onSaved(result.data);
    else setError(messageFor(result.response.status, result.error));
  }

  return (
    <form onSubmit={submit} className="flex flex-col gap-4">
      <div>
        <label htmlFor={`${id}-content`} className="mb-1.5 block text-xs text-fg-secondary">
          Runbook (markdown with front matter)
        </label>
        <Textarea
          id={`${id}-content`}
          value={content}
          onChange={(e) => setContent(e.target.value)}
          rows={18}
          spellCheck={false}
          aria-invalid={error ? true : undefined}
          aria-describedby={error ? `${id}-error` : undefined}
          className="font-mono text-xs leading-relaxed"
        />
      </div>
      {error && (
        <p id={`${id}-error`} role="alert" className="text-sm text-critical">
          {error}
        </p>
      )}
      <div className="flex justify-end">
        <Button type="submit" disabled={saving}>
          {saving ? "Saving…" : runbook ? "Save new version" : "Create runbook"}
        </Button>
      </div>
    </form>
  );
}
