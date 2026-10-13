import { Suspense } from "react";

import { SystemStatus } from "@/components/system-status";
import { UserMenu, UserMenuSkeleton } from "@/components/user-menu";

export default function Home() {
  return (
    <>
      <header className="border-b border-border bg-surface-1/60 backdrop-blur">
        <div className="mx-auto flex h-14 max-w-5xl items-center justify-between gap-4 px-4 sm:px-6">
          <div className="flex items-center gap-2.5">
            <span aria-hidden className="size-3 rotate-45 rounded-[3px] bg-accent shadow-[0_0_12px_var(--accent-subtle)]" />
            <span className="text-sm font-semibold tracking-tight">OpsPilot</span>
          </div>
          <Suspense fallback={<UserMenuSkeleton />}>
            <UserMenu />
          </Suspense>
        </div>
      </header>

      <main className="mx-auto w-full max-w-5xl flex-1 px-4 py-12 sm:px-6 sm:py-16">
        <p className="font-mono text-xs uppercase tracking-[0.18em] text-accent">Command Center</p>
        <h1 className="mt-3 text-3xl font-semibold tracking-tight sm:text-4xl">System status</h1>
        <p className="mt-3 max-w-xl text-fg-secondary">
          Live readiness of the OpsPilot platform and the dependencies it needs to detect and
          investigate incidents.
        </p>

        <div className="mt-10 max-w-xl">
          <SystemStatus />
        </div>
      </main>
    </>
  );
}
