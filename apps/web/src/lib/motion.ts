import type { Transition } from "motion/react";

/** Durations in seconds, mirroring the --duration-* tokens in globals.css. */
export const duration = {
  instant: 0.1,
  fast: 0.15,
  base: 0.22,
  slow: 0.32,
} as const;

/** Cubic béziers mirroring --ease-out and --ease-in-out. */
export const ease = {
  out: [0.16, 1, 0.3, 1],
  inOut: [0.65, 0, 0.35, 1],
} as const;

/** Spring presets from the interface v2 motion language. */
export const spring = {
  /** Highlights, toggles, the nav indicator. */
  snappy: { type: "spring", stiffness: 520, damping: 42, mass: 1 },
  /** Layout and shared-element transitions. */
  smooth: { type: "spring", stiffness: 320, damping: 34, mass: 1 },
  /** Animated numbers and tilt. */
  gentle: { type: "spring", stiffness: 170, damping: 26, mass: 1 },
} as const satisfies Record<string, Transition>;

/** Lists stagger by 30 ms, capped so long lists never feel slow. */
export const STAGGER_SECONDS = 0.03;
export const STAGGER_CAP = 8;

export function staggerDelay(index: number): number {
  return Math.min(index, STAGGER_CAP) * STAGGER_SECONDS;
}

/** The standard enter: fade in and rise a few pixels. */
export const enter = {
  initial: { opacity: 0, y: 6 },
  animate: { opacity: 1, y: 0 },
  exit: { opacity: 0, y: -4, transition: { duration: duration.fast, ease: ease.out } },
  transition: { duration: duration.base, ease: ease.out },
} as const;
