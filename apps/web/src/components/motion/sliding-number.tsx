"use client";

import { m, useReducedMotion as useMotionReduced } from "motion/react";

import { spring } from "@/lib/motion";

/** One digit column; the strip of 0–9 slides so the current digit shows. */
function Digit({ digit, reduced }: { digit: number; reduced: boolean }) {
  return (
    <span className="relative inline-block h-[1lh] w-[1ch] overflow-hidden">
      <m.span
        className="absolute inset-x-0 top-0 flex flex-col"
        initial={false}
        animate={{ y: `${-digit * 10}%` }}
        transition={reduced ? { duration: 0 } : spring.snappy}
      >
        {Array.from({ length: 10 }, (_, n) => (
          <span key={n} className="h-[1lh] text-center">
            {n}
          </span>
        ))}
      </m.span>
    </span>
  );
}

/**
 * A count whose digits slide like an odometer (Sliding Number, after Motion
 * Primitives). The visual digits are hidden from assistive technology; the
 * plain value is announced instead.
 */
export function SlidingNumber({ value, className }: { value: number; className?: string }) {
  const reduced = useMotionReduced() ?? false;
  const digits = String(Math.max(0, Math.round(value)))
    .split("")
    .map(Number);
  return (
    <span className={`tabular inline-flex ${className ?? ""}`}>
      <span aria-hidden className="inline-flex">
        {digits.map((digit, i) => (
          // Keyed from the right so units stay put when the number grows.
          <Digit key={digits.length - i} digit={digit} reduced={reduced} />
        ))}
      </span>
      <span className="sr-only">{value}</span>
    </span>
  );
}
