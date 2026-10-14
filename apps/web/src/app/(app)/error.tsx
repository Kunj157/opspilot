"use client";

import { useEffect } from "react";

import { Button } from "@/components/ui/button";

/** Recoverable error boundary for signed-in pages. Never shows the raw error. */
export default function ErrorBoundary({ error, reset }: { error: Error & { digest?: string }; reset: () => void }) {
  useEffect(() => {
    console.error("page error", error.digest ?? error.name);
  }, [error]);

  return (
    <main className="w-full max-w-5xl flex-1 px-4 py-10 sm:px-8 sm:py-12">
      <div
        role="alert"
        className="flex flex-col items-start gap-4 rounded-card border border-border bg-surface-2 p-6 shadow-3"
      >
        <div>
          <p className="text-lg font-semibold">Something went wrong</p>
          <p className="mt-1 text-sm text-fg-secondary">
            This page could not be displayed. Your data is safe; try again in a moment.
          </p>
        </div>
        <Button onClick={reset}>Try again</Button>
      </div>
    </main>
  );
}
