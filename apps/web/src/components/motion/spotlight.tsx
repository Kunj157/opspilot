"use client";

import { m, useMotionTemplate, useMotionValue, useSpring } from "motion/react";
import { type PointerEvent, type ReactNode, useState } from "react";

import { spring } from "@/lib/motion";
import { useReducedMotion } from "@/lib/use-reduced-motion";

/**
 * A soft Iris light that follows the pointer across a surface (Spotlight, after
 * Motion Primitives). Only for fine pointers; nothing renders under reduced
 * motion or before the first pointer move.
 */
export function Spotlight({ children, className, size = 320 }: { children: ReactNode; className?: string; size?: number }) {
  const reduced = useReducedMotion();
  const [active, setActive] = useState(false);
  const x = useSpring(useMotionValue(0), spring.gentle);
  const y = useSpring(useMotionValue(0), spring.gentle);
  const background = useMotionTemplate`radial-gradient(${size}px circle at ${x}px ${y}px, var(--accent-subtle), transparent 70%)`;

  function move(event: PointerEvent<HTMLDivElement>) {
    if (reduced || event.pointerType !== "mouse") return;
    const box = event.currentTarget.getBoundingClientRect();
    x.set(event.clientX - box.left);
    y.set(event.clientY - box.top);
    setActive(true);
  }

  return (
    <div className={`relative ${className ?? ""}`} onPointerMove={move} onPointerLeave={() => setActive(false)}>
      {active && (
        <m.div
          aria-hidden
          data-testid="spotlight"
          className="pointer-events-none absolute inset-0 rounded-[inherit]"
          style={{ background }}
          initial={{ opacity: 0 }}
          animate={{ opacity: 1 }}
        />
      )}
      {children}
    </div>
  );
}
