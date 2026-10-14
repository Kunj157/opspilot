"use client";

import dynamic from "next/dynamic";
import { createContext, type ReactNode, useCallback, useContext, useState } from "react";

const ToastList = dynamic(() => import("./toast-list"), { ssr: false });

type Tone = "success" | "error";
export type Toast = { id: number; message: string; tone: Tone };
type Notify = (message: string, tone?: Tone) => void;

const TOAST_MS = 5000;
const ToastContext = createContext<Notify | null>(null);
let nextId = 0;

export function useToast(): Notify {
  const notify = useContext(ToastContext);
  if (!notify) throw new Error("useToast must be used inside <ToastProvider>");
  return notify;
}

/** Transient notifications; errors are announced assertively, the rest politely. */
export function ToastProvider({ children }: { children: ReactNode }) {
  const [toasts, setToasts] = useState<Toast[]>([]);
  const [used, setUsed] = useState(false);
  const dismiss = useCallback((id: number) => setToasts((all) => all.filter((t) => t.id !== id)), []);
  const notify = useCallback<Notify>(
    (message, tone = "success") => {
      const id = ++nextId;
      setUsed(true);
      setToasts((all) => [...all, { id, message, tone }]);
      setTimeout(() => dismiss(id), TOAST_MS);
    },
    [dismiss],
  );

  const region = (tone: Tone) => (
    // Live regions without a landmark role, so page-level status and alert queries stay unambiguous.
    <section
      aria-label={tone === "error" ? "Error messages" : "Notifications"}
      aria-live={tone === "error" ? "assertive" : "polite"}
      className="pointer-events-none fixed right-4 bottom-4 z-50 w-[min(24rem,calc(100vw-2rem))]"
    >
      {used && <ToastList toasts={toasts.filter((t) => t.tone === tone)} dismiss={dismiss} lifetime={TOAST_MS} />}
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
