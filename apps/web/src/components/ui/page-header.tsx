import type { ReactNode } from "react";

/**
 * The top of every page: a mono eyebrow in Iris, the page title (the LCP
 * element, plain server-rendered text with no animation), an optional
 * description, and actions aligned to the right on wide screens.
 */
export function PageHeader({
  eyebrow,
  title,
  description,
  actions,
}: {
  eyebrow: string;
  title: ReactNode;
  description?: ReactNode;
  actions?: ReactNode;
}) {
  return (
    <header className="flex flex-col gap-4 sm:flex-row sm:items-end sm:justify-between">
      <div className="min-w-0">
        <p className="font-mono text-xs tracking-[0.18em] text-accent uppercase">{eyebrow}</p>
        <h1 className="mt-3 text-3xl font-semibold tracking-tight text-balance sm:text-4xl">{title}</h1>
        {description && <p className="mt-3 max-w-xl text-pretty text-fg-secondary">{description}</p>}
      </div>
      {actions && <div className="flex shrink-0 items-center gap-2">{actions}</div>}
    </header>
  );
}
