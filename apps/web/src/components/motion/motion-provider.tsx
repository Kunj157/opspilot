"use client";

import { LazyMotion, MotionConfig } from "motion/react";
import type { ReactNode } from "react";

import { duration, ease } from "@/lib/motion";

const loadFeatures = () => import("./features").then((module) => module.default);

/**
 * Root of all motion. Features (including layout animations) load lazily after
 * hydration; `strict` keeps components on the lightweight `m.*` elements.
 * `reducedMotion="user"` turns transform and layout animations off for users
 * who prefer reduced motion — components that animate anything else check
 * `useReducedMotion()` themselves.
 */
export function MotionProvider({ children }: { children: ReactNode }) {
  return (
    <LazyMotion features={loadFeatures} strict>
      <MotionConfig reducedMotion="user" transition={{ duration: duration.base, ease: ease.out }}>
        {children}
      </MotionConfig>
    </LazyMotion>
  );
}
