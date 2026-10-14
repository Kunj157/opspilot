"use client";

import {
  type ComponentPropsWithoutRef,
  type ComponentType,
  type ElementType,
  type HTMLAttributes,
  type PointerEvent,
  type Ref,
  useRef,
} from "react";

import { useReducedMotion } from "@/lib/use-reduced-motion";

const MAX_TILT_DEGREES = 4;

type CardProps<T extends ElementType> = {
  as?: T;
  /** Lean toward the pointer (§16.1); off under reduced motion. */
  tilt?: boolean;
} & ComponentPropsWithoutRef<T>;

/** An elevated surface-2 panel with the standard border, radius, and shadow. */
export function Card<T extends ElementType = "div">({
  as,
  tilt = false,
  className = "",
  onPointerMove,
  onPointerLeave,
  ...props
}: CardProps<T>) {
  // Narrowed on purpose: three.js JSX elements make the full ElementType union too large to check.
  const Component = (as ?? "div") as ComponentType<HTMLAttributes<HTMLElement> & { ref?: Ref<HTMLElement> }>;
  const ref = useRef<HTMLElement>(null);
  const reduced = useReducedMotion();
  const tilting = tilt && !reduced;

  function move(event: PointerEvent<HTMLElement>) {
    onPointerMove?.(event);
    const node = ref.current;
    if (!tilting || !node) return;
    const box = node.getBoundingClientRect();
    const x = ((event.clientX - box.left) / box.width - 0.5) * 2;
    const y = ((event.clientY - box.top) / box.height - 0.5) * 2;
    const round = (n: number) => Math.round(n * 100) / 100 || 0;
    node.style.transform = `perspective(800px) rotateX(${round(-y * MAX_TILT_DEGREES)}deg) rotateY(${round(x * MAX_TILT_DEGREES)}deg)`;
  }

  function leave(event: PointerEvent<HTMLElement>) {
    onPointerLeave?.(event);
    if (ref.current) ref.current.style.transform = "";
  }

  return (
    <Component
      ref={ref}
      onPointerMove={move}
      onPointerLeave={leave}
      className={`surface-raised rounded-card border border-border ${
        tilting ? "transition-transform duration-base will-change-transform" : ""
      } ${className}`}
      {...props}
    />
  );
}
