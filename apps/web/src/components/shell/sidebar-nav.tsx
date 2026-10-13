"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";

import { icons } from "@/components/icons";

import { isActive, type NavItem } from "./nav-items";

export function SidebarNav({ items, onNavigate }: { items: NavItem[]; onNavigate?: () => void }) {
  const pathname = usePathname();
  return (
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
                className={`flex items-center gap-2.5 rounded-sm px-3 py-2 text-sm transition-colors duration-base ${
                  active
                    ? "bg-surface-3 text-fg shadow-1"
                    : "text-fg-secondary hover:bg-surface-2 hover:text-fg"
                }`}
              >
                <Icon className={active ? "text-accent" : "text-fg-muted"} />
                {item.label}
              </Link>
            </li>
          );
        })}
      </ul>
    </nav>
  );
}
