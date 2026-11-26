"use client";

import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { type ReactNode, useEffect, useState } from "react";

import { ToastProvider } from "@/components/ui/toast";

let browserQueryClient: QueryClient | undefined;

function getQueryClient() {
  // Keep server renders isolated and reuse one client in the browser.
  if (typeof window === "undefined") return new QueryClient();
  browserQueryClient ??= new QueryClient();
  return browserQueryClient;
}

const DEMO = process.env.NEXT_PUBLIC_DEMO === "1";

export function Providers({ children }: { children: ReactNode }) {
  // Demo build only: load the in-browser API before anything fetches. Outside the
  // demo the condition is false at build time, so the demo code is not bundled.
  const [ready, setReady] = useState(!DEMO);
  useEffect(() => {
    if (process.env.NEXT_PUBLIC_DEMO === "1") void import("@/demo/runtime").then(() => setReady(true));
  }, []);
  if (!ready) return null;
  return (
    <QueryClientProvider client={getQueryClient()}>
      <ToastProvider>{children}</ToastProvider>
    </QueryClientProvider>
  );
}
