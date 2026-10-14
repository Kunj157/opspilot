"use client";

import { m } from "motion/react";
import { type ReactNode, useState } from "react";

import { duration, ease } from "@/lib/motion";

/**
 * Slides each new panel in from the direction of travel (Transition Panel,
 * after Motion Primitives). Enter-only on purpose: the outgoing panel leaves
 * at once, so there is never a second tab panel in the accessibility tree.
 * The first panel renders without animation.
 */
export function TransitionPanel({
  activeKey,
  direction = 1,
  children,
  className,
}: {
  activeKey: string;
  /** 1 when moving forward (e.g. to a later tab), -1 when moving back. */
  direction?: 1 | -1;
  children: ReactNode;
  className?: string;
}) {
  const [first] = useState(activeKey);
  return (
    <m.div
      key={activeKey}
      className={className}
      initial={activeKey === first ? false : { opacity: 0, x: 10 * direction }}
      animate={{ opacity: 1, x: 0 }}
      transition={{ duration: duration.base, ease: ease.out }}
    >
      {children}
    </m.div>
  );
}
