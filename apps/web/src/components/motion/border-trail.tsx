"use client";

/**
 * Adapted from Motion Primitives' Border Trail
 * (https://github.com/ibelick/motion-primitives, components/core/border-trail.tsx).
 *
 * MIT License — Copyright (c) 2024 Julien Thibeaut (ibelick).
 * Permission is hereby granted, free of charge, to any person obtaining a copy
 * of this software and associated documentation files (the "Software"), to deal
 * in the Software without restriction, including without limitation the rights
 * to use, copy, modify, merge, publish, distribute, sublicense, and/or sell
 * copies of the Software, and to permit persons to whom the Software is
 * furnished to do so, subject to the following conditions: The above copyright
 * notice and this permission notice shall be included in all copies or
 * substantial portions of the Software. THE SOFTWARE IS PROVIDED "AS IS",
 * WITHOUT WARRANTY OF ANY KIND.
 *
 * Changes: Iris token colour and glow, renders nothing under reduced motion.
 */
import { m } from "motion/react";

import { useReducedMotion } from "@/lib/use-reduced-motion";

/** A short light travelling around the parent's border; marks live agent activity. */
export function BorderTrail({ size = 72, seconds = 4 }: { size?: number; seconds?: number }) {
  const reduced = useReducedMotion();
  if (reduced) return null;
  return (
    <div
      aria-hidden
      data-testid="border-trail"
      className="pointer-events-none absolute inset-0 rounded-[inherit] border border-transparent [mask-clip:padding-box,border-box] [mask-composite:intersect] [mask-image:linear-gradient(transparent,transparent),linear-gradient(black,black)]"
    >
      <m.div
        className="absolute aspect-square bg-[radial-gradient(circle,var(--accent),transparent_70%)]"
        style={{ width: size, offsetPath: `rect(0 auto auto 0 round ${size}px)` }}
        animate={{ offsetDistance: ["0%", "100%"] }}
        transition={{ repeat: Infinity, duration: seconds, ease: "linear" }}
      />
    </div>
  );
}
