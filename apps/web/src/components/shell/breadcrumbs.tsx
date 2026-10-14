"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";

import { NAV_ITEMS } from "./nav-items";

const DETAIL: Record<string, string> = {
  "/incidents": "Incident",
  "/services": "Service",
  "/runbooks": "Runbook",
};

/** Where am I: the section, and "Incident"/"Service"/… on detail pages. */
export function trail(pathname: string): { label: string; href?: string }[] {
  const [, first, second] = pathname.split("/");
  const section = NAV_ITEMS.find((item) => item.href === `/${first ?? ""}`);
  if (!section) return [];
  if (!second) return [{ label: section.label }];
  return [{ label: section.label, href: section.href }, { label: DETAIL[section.href] ?? "Details" }];
}

export function Breadcrumbs() {
  const crumbs = trail(usePathname());
  if (crumbs.length === 0) return null;
  return (
    <nav aria-label="Breadcrumb" className="min-w-0">
      <ol className="flex items-center gap-1.5 truncate text-sm">
        {crumbs.map((crumb, i) => (
          <li key={crumb.label} className="flex min-w-0 items-center gap-1.5">
            {i > 0 && (
              <span aria-hidden className="text-fg-muted">
                /
              </span>
            )}
            {crumb.href ? (
              <Link href={crumb.href} className="truncate text-fg-secondary hover:text-fg">
                {crumb.label}
              </Link>
            ) : (
              <span aria-current="page" className="truncate font-medium text-fg">
                {crumb.label}
              </span>
            )}
          </li>
        ))}
      </ol>
    </nav>
  );
}
