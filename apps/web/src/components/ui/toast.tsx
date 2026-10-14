"use client";

import { AnimatePresence, m } from "motion/react";
import { createContext, type ReactNode, useCallback, useContext, useEffect, useState } from "react";

import { icons } from "@/components/icons";
import { MotionScope } from "@/components/motion/motion-provider";
import { duration, ease, spring } from "@/lib/motion";

type Tone = "success" | "error";
type Toast = { id: number; message: string; tone: Tone };
type Notify = (message: string, tone?: Tone) => void;

const TOAST_MS = 5000;
const ToastContext = createContext<Notify | null>(null);
let nextId = 0;

export function useToast(): Notify {
  const notify = useContext(ToastContext);
  if (!notify) throw new Error("useToast must be used inside <ToastProvider>");
  return notify;
}

function ToastItem({ toast, dismiss }: { toast: Toast; dismiss: (id: number) => void }) {
  useEffect(() => {
    const timer = setTimeout(() => dismiss(toast.id), TOAST_MS);
    return () => clearTimeout(timer);
  }, [toast.id, dismiss]);

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
        style={{ animationDuration: `${TOAST_MS}ms` }}
      />
    </m.li>
  );
}

/** Transient notifications; errors are announced assertively, the rest politely. */
export function ToastProvider({ children }: { children: ReactNode }) {
  const [toasts, setToasts] = useState<Toast[]>([]);
  const notify = useCallback<Notify>((message, tone = "success") => {
    setToasts((all) => [...all, { id: ++nextId, message, tone }]);
  }, []);
  const dismiss = useCallback((id: number) => setToasts((all) => all.filter((t) => t.id !== id)), []);

  const region = (tone: Tone) => (
    // Live regions without a landmark role, so page-level status and alert queries stay unambiguous.
    <section
      aria-label={tone === "error" ? "Error messages" : "Notifications"}
      aria-live={tone === "error" ? "assertive" : "polite"}
      className="pointer-events-none fixed right-4 bottom-4 z-50 w-[min(24rem,calc(100vw-2rem))]"
    >
      <MotionScope>
        <ul className="flex flex-col gap-2">
          <AnimatePresence initial={false}>
            {toasts
              .filter((t) => t.tone === tone)
              .map((t) => (
                <ToastItem key={t.id} toast={t} dismiss={dismiss} />
              ))}
          </AnimatePresence>
        </ul>
      </MotionScope>
    </section>
  );

  return (
    <ToastContext.Provider value={notify}>
      {children}
      {region("success")}
      {region("error")}
    </ToastContext.Provider>
  );
}
