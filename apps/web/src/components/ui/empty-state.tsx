import type { ReactNode } from "react";

/**
 * A calm, centred empty state: a small layered illustration, a title, an
 * explanation, and an optional next step. The illustration is decorative.
 */
export function EmptyState({
  title,
  description,
  action,
  tone = "neutral",
}: {
  title: string;
  description?: ReactNode;
  action?: ReactNode;
  /** "positive" for good news such as "all quiet". */
  tone?: "neutral" | "positive";
}) {
  return (
    <div className="flex flex-col items-center gap-3 px-6 py-12 text-center">
      <svg aria-hidden width="72" height="56" viewBox="0 0 72 56" fill="none" className="mb-1">
        <rect x="14" y="14" width="44" height="30" rx="7" className="fill-surface-3 stroke-border-strong" />
        <rect x="8" y="20" width="56" height="30" rx="8" className="fill-surface-2 stroke-border-strong" />
        <path d="M22 35h16M22 41h10" className="stroke-fg-muted" strokeWidth="2" strokeLinecap="round" />
        <circle
          cx="52"
          cy="38"
          r="5"
          className={tone === "positive" ? "fill-healthy-subtle stroke-healthy" : "fill-accent-subtle stroke-accent"}
          strokeWidth="1.5"
        />
      </svg>
      <p className="text-sm font-medium text-fg">{title}</p>
      {description && <p className="max-w-sm text-sm text-fg-muted">{description}</p>}
      {action && <div className="mt-2">{action}</div>}
    </div>
  );
}

/** A keyboard key, e.g. <Kbd>⌘</Kbd><Kbd>K</Kbd>. */
export function Kbd({ children }: { children: ReactNode }) {
  return (
    <kbd className="inline-flex h-5 min-w-5 items-center justify-center rounded-[5px] border border-border-strong bg-surface-3 px-1 font-mono text-[11px] text-fg-secondary shadow-edge">
      {children}
    </kbd>
  );
}
