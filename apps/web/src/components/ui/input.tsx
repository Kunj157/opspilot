import type { ComponentProps } from "react";

import { icons } from "@/components/icons";

/** Shared look for every text-like control: surface-1 well, Iris focus, critical when invalid. */
export const controlClass =
  "w-full rounded-sm border border-border bg-surface-1 text-sm text-fg shadow-edge placeholder:text-fg-muted transition-[border-color,box-shadow] duration-(--duration-fast) hover:border-border-strong focus-visible:border-accent focus-visible:shadow-glow-accent focus-visible:outline-none aria-[invalid=true]:border-critical disabled:opacity-50";

export function Input({ className = "", ...props }: ComponentProps<"input">) {
  return <input className={`h-9 px-2.5 ${controlClass} ${className}`} {...props} />;
}

export function Textarea({ className = "", ...props }: ComponentProps<"textarea">) {
  return <textarea className={`px-2.5 py-2 ${controlClass} ${className}`} {...props} />;
}

/** A native select (keyboard and screen-reader behaviour for free) with our chevron. */
export function Select({ className = "", children, ...props }: ComponentProps<"select">) {
  return (
    <span className={`relative block ${className}`}>
      <select className={`h-9 appearance-none pr-8 pl-2.5 ${controlClass}`} {...props}>
        {children}
      </select>
      <icons.chevron aria-hidden className="pointer-events-none absolute top-1/2 right-2.5 -translate-y-1/2 text-fg-muted" />
    </span>
  );
}

export function Checkbox({ className = "", ...props }: Omit<ComponentProps<"input">, "type">) {
  return <input type="checkbox" className={`size-4 rounded-[4px] accent-(--accent) ${className}`} {...props} />;
}
