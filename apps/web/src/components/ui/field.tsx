"use client";

import { type ReactNode, useId } from "react";

/** Props a control needs to be labelled, described, and marked invalid. */
export type FieldControl = {
  id: string;
  required?: boolean;
  "aria-invalid"?: true;
  "aria-describedby"?: string;
};

/**
 * Label, optional hint, and error message wired to one control. The control
 * receives `id`, `aria-invalid`, and `aria-describedby` through the render prop,
 * so any input, select, or textarea (and react-hook-form's `register`) fits.
 */
export function Field({
  label,
  hint,
  error,
  required,
  className,
  children,
}: {
  label: ReactNode;
  hint?: ReactNode;
  error?: string;
  required?: boolean;
  className?: string;
  children: (control: FieldControl) => ReactNode;
}) {
  const id = useId();
  const hintId = hint ? `${id}-hint` : undefined;
  const errorId = error ? `${id}-error` : undefined;
  const describedBy = [errorId, hintId].filter(Boolean).join(" ") || undefined;
  return (
    <div className={className}>
      <div className="mb-1.5 flex gap-1 text-xs text-fg-secondary">
        <label htmlFor={id}>{label}</label>
        {/* Visual hint only; the control's required attribute is what assistive tech reads. */}
        {required && (
          <span aria-hidden className="text-accent">
            *
          </span>
        )}
      </div>
      {children({ id, required, "aria-invalid": error ? true : undefined, "aria-describedby": describedBy })}
      {hint && !error && (
        <p id={hintId} className="mt-1 text-xs text-fg-muted">
          {hint}
        </p>
      )}
      {error && (
        <p id={errorId} className="mt-1 text-xs text-critical">
          {error}
        </p>
      )}
    </div>
  );
}
