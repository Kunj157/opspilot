"use client";

import { m } from "motion/react";
import type { ReactNode } from "react";

import { duration, ease, staggerDelay } from "@/lib/motion";

/**
 * Fades and lifts its children in the first time they scroll into view
 * (In View, after Motion Primitives). Content is in the DOM from the start,
 * only its opacity and offset animate; reduced motion shows it immediately.
 */
export function InView({
  children,
  index = 0,
  className,
}: {
  children: ReactNode;
  /** Position in a group, for a capped stagger. */
  index?: number;
  className?: string;
}) {
  return (
    <m.div
      className={className}
      initial={{ opacity: 0, y: 8 }}
      whileInView={{ opacity: 1, y: 0 }}
      viewport={{ once: true, margin: "0px 0px -40px 0px" }}
      transition={{ duration: duration.slow, ease: ease.out, delay: staggerDelay(index) }}
    >
      {children}
    </m.div>
  );
}
