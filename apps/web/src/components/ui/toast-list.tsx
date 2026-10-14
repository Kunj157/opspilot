"use client";

import { AnimatePresence, m } from "motion/react";

import { icons } from "@/components/icons";
import { MotionScope } from "@/components/motion/motion-provider";
import { duration, ease, spring } from "@/lib/motion";

import type { Toast } from "./toast";

function ToastItem({ toast, dismiss, lifetime }: { toast: Toast; dismiss: (id: number) => void; lifetime: number }) {
  const error = toast.tone === "error";
  return (
    <m.li
      layout
      initial={{ opacity: 0, x: 24, scale: 0.98 }}
      animate={{ opacity: 1, x: 0, scale: 1 }}
      exit={{ opacity: 0, x: 24, transition: { duration: duration.fast, ease: ease.out } }}
      transition={spring.smooth}
      className="pointer-events-auto relative flex items-start gap-3 overflow-hidden rounded-card border border-border-strong bg-surface-glass px-4 py-3 text-sm shadow-3 backdrop-blur-md"
    >
      <span
        aria-hidden
        className={`mt-0.5 grid size-4 shrink-0 place-items-center rounded-full text-[10px] font-bold ${
          error ? "bg-critical-subtle text-critical" : "bg-healthy-subtle text-healthy"
        }`}
      >
        {error ? "!" : "✓"}
      </span>
      <p className="flex-1">{toast.message}</p>
      <button type="button" onClick={() => dismiss(toast.id)} aria-label="Dismiss" className="rounded-sm text-fg-secondary hover:text-fg">
        <icons.close />
      </button>
      {/* Time left before it goes away; the global reduced-motion rule makes it static. */}
      <span
        aria-hidden
        className={`toast-timer absolute bottom-0 left-0 h-px w-full origin-left ${error ? "bg-critical" : "bg-accent"}`}
        style={{ animationDuration: `${lifetime}ms` }}
      />
    </m.li>
  );
}

/** The animated stack, loaded with the first toast so pages ship no motion code for it. */
export default function ToastList({
  toasts,
  dismiss,
  lifetime,
}: {
  toasts: Toast[];
  dismiss: (id: number) => void;
  lifetime: number;
}) {
  return (
    <MotionScope>
      <ul className="flex flex-col gap-2">
        <AnimatePresence initial={false}>
          {toasts.map((t) => (
            <ToastItem key={t.id} toast={t} dismiss={dismiss} lifetime={lifetime} />
          ))}
        </AnimatePresence>
      </ul>
    </MotionScope>
  );
}
