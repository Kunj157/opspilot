import { Suspense } from "react";

import { LoginPanel } from "./login-panel";

export const metadata = { title: "Sign in · OpsPilot" };

export default function LoginPage() {
  return (
    <main className="flex flex-1 items-center justify-center px-4 py-16">
      <div className="w-full max-w-sm [perspective:1200px]">
        <div className="relative overflow-hidden rounded-lg border border-border bg-surface-2 p-8 shadow-3 transition-transform duration-base [transform:rotateX(2deg)] hover:[transform:rotateX(0deg)] motion-reduce:[transform:none]">
          <div aria-hidden className="absolute inset-x-0 top-0 h-px bg-gradient-to-r from-transparent via-white/15 to-transparent" />
          <div className="flex items-center gap-2.5">
            <span aria-hidden className="size-3.5 rotate-45 rounded-[3px] bg-accent shadow-[0_0_14px_var(--accent-subtle)]" />
            <span className="text-base font-semibold tracking-tight">OpsPilot</span>
          </div>
          <h1 className="mt-8 text-2xl font-semibold tracking-tight">Sign in</h1>
          <p className="mt-2 text-sm text-fg-secondary">
            Use your organization&apos;s single sign-on to open the command center.
          </p>
          <Suspense fallback={<div className="mt-8 h-11 rounded-card bg-surface-3" />}>
            <LoginPanel />
          </Suspense>
        </div>
      </div>
    </main>
  );
}
