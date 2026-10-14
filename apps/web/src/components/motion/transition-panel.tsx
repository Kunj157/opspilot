"use client";

import { AnimatePresence, m } from "motion/react";
import type { ReactNode } from "react";

import { duration, ease } from "@/lib/motion";

/**
 * Cross-fades between panels keyed by `activeKey`, sliding a few pixels in the
 * direction of travel (Transition Panel, after Motion Primitives).
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
  return (
    <AnimatePresence mode="popLayout" initial={false} custom={direction}>
      <m.div
        key={activeKey}
        className={className}
        custom={direction}
        variants={{
          enter: (d: number) => ({ opacity: 0, x: 12 * d }),
          center: { opacity: 1, x: 0 },
          exit: (d: number) => ({ opacity: 0, x: -12 * d }),
        }}
        initial="enter"
        animate="center"
        exit="exit"
        transition={{ duration: duration.base, ease: ease.out }}
      >
        {children}
      </m.div>
    </AnimatePresence>
  );
}
