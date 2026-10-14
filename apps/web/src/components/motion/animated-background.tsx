"use client";

import { m } from "motion/react";

import { spring } from "@/lib/motion";

/**
 * The sliding highlight behind the active item of a nav, tab list, or segmented
 * control (Animated Background, after Motion Primitives). Render it inside the
 * active item only; items sharing a `layoutId` hand the highlight over with a
 * spring. Place it first in a `relative` parent so the item's content sits on top.
 */
export function ActiveHighlight({ layoutId, className }: { layoutId: string; className?: string }) {
  return (
    <m.span
      aria-hidden
      layoutId={layoutId}
      transition={spring.snappy}
      className={`absolute inset-0 -z-10 ${className ?? ""}`}
    />
  );
}
