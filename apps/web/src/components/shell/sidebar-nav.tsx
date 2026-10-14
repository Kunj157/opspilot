"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";

import { icons } from "@/components/icons";
import { ActiveHighlight } from "@/components/motion/animated-background";
import { MotionScope } from "@/components/motion/motion-provider";

import { isActive, type NavItem } from "./nav-items";

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
                </Link>
              </li>
            );
          })}
        </ul>
      </nav>
    </MotionScope>
  );
}
