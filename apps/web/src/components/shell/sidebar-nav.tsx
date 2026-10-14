"use client";

import { createApiClient } from "@opspilot/api-client";
import { useQuery } from "@tanstack/react-query";
import Link from "next/link";
import { usePathname } from "next/navigation";

import { icons } from "@/components/icons";
import { ActiveHighlight } from "@/components/motion/animated-background";
import { MotionScope } from "@/components/motion/motion-provider";
import { SlidingNumber } from "@/components/motion/sliding-number";

import { isActive, type NavItem } from "./nav-items";

/** Open incidents across the organization, for the badge beside "Incidents". */
function useOpenIncidents(enabled: boolean): number | null {
  const metrics = useQuery({
    queryKey: ["incidents", "open-count"],
    enabled,
    queryFn: async ({ signal }) => {
      const { data } = await createApiClient(window.location.origin).GET("/api/v1/incident-metrics", {
        params: { query: { days: 1 } },
        signal,
      });
      if (!data) throw new Error("metrics unavailable");
      return Object.values(data.active_by_severity).reduce((sum, n) => sum + n, 0);
    },
    refetchInterval: 30_000,
  });
  return metrics.data ?? null;
}

export function SidebarNav({
  items,
  onNavigate,
  highlightId = "nav-highlight",
}: {
  items: NavItem[];
  onNavigate?: () => void;
  /** Distinct per navigation instance, so the highlight never jumps between them. */
  highlightId?: string;
}) {
  const pathname = usePathname();
  const open = useOpenIncidents(items.some((item) => item.href === "/incidents"));
  return (
    <MotionScope>
      <nav aria-label="Main">
        <ul className="flex flex-col gap-0.5">
          {items.map((item) => {
            const active = isActive(item.href, pathname);
            const Icon = icons[item.icon];
            return (
              <li key={item.href}>
                <Link
                  href={item.href}
                  onClick={onNavigate}
                  aria-current={active ? "page" : undefined}
                  className={`group relative isolate flex items-center gap-2.5 rounded-sm px-3 py-2 text-sm transition-colors duration-(--duration-instant) ${
                    active ? "text-fg" : "text-fg-secondary hover:bg-surface-2/70 hover:text-fg"
                  }`}
                >
                  {active && (
                    <ActiveHighlight
                      layoutId={highlightId}
                      className="rounded-sm border border-border bg-surface-3 shadow-edge"
                    />
                  )}
                  {active && (
                    <span aria-hidden className="absolute top-2 bottom-2 -left-4 w-0.5 rounded-full bg-accent shadow-glow-accent" />
                  )}
                  <Icon className={active ? "text-accent" : "text-fg-muted transition-colors group-hover:text-fg-secondary"} />
                  {item.label}
                  {/* Visual only: the incidents page states the count in words. */}
                  {item.href === "/incidents" && open !== null && open > 0 && (
                    <span
                      aria-hidden
                      className="ml-auto inline-flex h-5 items-center rounded-full border border-border bg-surface-1 px-1.5 font-mono text-[11px] leading-4 text-fg-secondary"
                    >
                      <SlidingNumber value={open} />
                    </span>
                  )}
                </Link>
              </li>
            );
          })}
        </ul>
      </nav>
    </MotionScope>
  );
}
