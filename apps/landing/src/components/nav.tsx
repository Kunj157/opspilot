"use client";

import { motion, useMotionValueEvent, useScroll } from "motion/react";
import { useState } from "react";

import { REPO } from "./links";

const LINKS = [
  ["Loop", "#loop"],
  ["Features", "#features"],
  ["Product", "#product"],
] as const;

/** A floating glass bar that tightens once the page scrolls. */
export function Nav() {
  const { scrollY } = useScroll();
  const [scrolled, setScrolled] = useState(false);
  useMotionValueEvent(scrollY, "change", (y) => setScrolled(y > 24));

  return (
    <header className="fixed inset-x-0 top-3 z-50 flex justify-center px-4">
      <motion.nav
        aria-label="Main"
        animate={{ maxWidth: scrolled ? 760 : 1180, paddingTop: scrolled ? 8 : 12, paddingBottom: scrolled ? 8 : 12 }}
        transition={{ type: "spring", stiffness: 260, damping: 30 }}
        className="flex w-full items-center justify-between gap-4 rounded-full border border-border bg-surface-glass px-5 shadow-2 backdrop-blur-xl"
      >
        <a href="#" className="flex items-center gap-2 font-semibold tracking-tight">
          <span aria-hidden className="size-3 rotate-45 rounded-[3px] bg-accent shadow-glow-accent" />
          OpsPilot
        </a>
        <ul className="hidden items-center gap-6 text-sm text-fg-secondary sm:flex">
          {LINKS.map(([label, href]) => (
            <li key={href}>
              <a href={href} className="transition-colors hover:text-fg">
                {label}
              </a>
            </li>
          ))}
        </ul>
        <a
          href={REPO}
          className="rounded-full border border-border-strong px-3.5 py-1.5 text-sm transition-colors hover:bg-surface-2"
        >
          GitHub
        </a>
      </motion.nav>
    </header>
  );
}
