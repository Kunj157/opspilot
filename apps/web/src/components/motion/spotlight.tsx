"use client";

import { type PointerEvent, type ReactNode, useRef, useState } from "react";

import { useReducedMotion } from "@/lib/use-reduced-motion";

/**
 * A soft Iris light that follows the pointer across a surface (Spotlight, after
 * Motion Primitives). Plain CSS custom properties, so pages that use it (the
 * sign-in page) ship no animation library. Only for a mouse; nothing renders
 * under reduced motion or before the first pointer move.
 */
export function Spotlight({ children, className, size = 320 }: { children: ReactNode; className?: string; size?: number }) {
  const reduced = useReducedMotion();
  const [active, setActive] = useState(false);
  const light = useRef<HTMLDivElement>(null);

  function move(event: PointerEvent<HTMLDivElement>) {
    if (reduced || event.pointerType !== "mouse") return;
    const box = event.currentTarget.getBoundingClientRect();
    light.current?.style.setProperty("--spot-x", `${event.clientX - box.left}px`);
    light.current?.style.setProperty("--spot-y", `${event.clientY - box.top}px`);
    setActive(true);
  }

  return (
    <div className={`relative ${className ?? ""}`} onPointerMove={move} onPointerLeave={() => setActive(false)}>
      {children}
      {/* Above the content, so the light washes over opaque surfaces too. */}
      {!reduced && (
        <div
          ref={light}
          aria-hidden
          data-testid={active ? "spotlight" : undefined}
          className={`pointer-events-none absolute inset-0 z-10 rounded-[inherit] transition-opacity duration-(--duration-base) ${
            active ? "opacity-100" : "opacity-0"
          }`}
          style={{
            background: `radial-gradient(${size}px circle at var(--spot-x, 50%) var(--spot-y, 50%), var(--accent-subtle), transparent 70%)`,
          }}
        />
      )}
    </div>
  );
}
