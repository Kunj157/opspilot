"use client";

import { createContext, type ReactNode, useCallback, useContext, useEffect, useState } from "react";

import { icons } from "@/components/icons";

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

  return (
    <li className="pointer-events-auto flex items-start gap-3 rounded-card border border-border bg-surface-3 px-4 py-3 text-sm shadow-3">
      <span aria-hidden className={`mt-1.5 size-2 shrink-0 rounded-full ${toast.tone === "error" ? "bg-critical" : "bg-healthy"}`} />
      <p className="flex-1">{toast.message}</p>
      <button type="button" onClick={() => dismiss(toast.id)} aria-label="Dismiss" className="text-fg-secondary hover:text-fg">
        <icons.close />
      </button>
    </li>
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
    <ul
      role={tone === "error" ? "alert" : "status"}
      className="pointer-events-none fixed right-4 bottom-4 z-50 flex w-[min(24rem,calc(100vw-2rem))] flex-col gap-2"
    >
      {toasts
        .filter((t) => t.tone === tone)
        .map((t) => (
          <ToastItem key={t.id} toast={t} dismiss={dismiss} />
        ))}
    </ul>
  );

  return (
    <ToastContext.Provider value={notify}>
      {children}
      {region("success")}
      {region("error")}
    </ToastContext.Provider>
  );
}
