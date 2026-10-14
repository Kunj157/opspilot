"use client";

import { LazyMotion, MotionConfig } from "motion/react";
import type { ReactNode } from "react";

import { duration, ease } from "@/lib/motion";

const loadFeatures = () => import("./features").then((module) => module.default);

/**
 * Wrap each client island that animates. Animation features (including layout
 * animations) load lazily after the island hydrates and stay off the critical
 * path; until then `m.*` elements render statically. `reducedMotion="user"`
 * turns transform and layout animations off for users who prefer reduced
 * motion; components that animate anything else check `useReducedMotion()`.
 *
 * Kept per island on purpose: a feature load at the app root is a context
 * change above server-streamed Suspense boundaries that have not hydrated yet,
 * which makes React client-render them while the streamed copy is still in
 * the document. Pages without animated islands (sign-in) ship no motion code.
 */
export function MotionScope({ children }: { children: ReactNode }) {
  return (
    <LazyMotion features={loadFeatures} strict>
      <MotionConfig reducedMotion="user" transition={{ duration: duration.base, ease: ease.out }}>
        {children}
      </MotionConfig>
    </LazyMotion>
  );
}
