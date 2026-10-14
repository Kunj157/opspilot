import { Suspense } from "react";

import { Spotlight } from "@/components/motion/spotlight";

import { LoginPanel } from "./login-panel";

export const metadata = { title: "Sign in · OpsPilot" };

/** A wireframe floor drifting toward a faint Iris horizon; pure CSS, still under reduced motion. */
function Horizon() {
  return (
    <div aria-hidden className="login-horizon">
      <div className="login-floor" />
    </div>
  );
}

export default function LoginPage() {
  return (
    <main className="relative flex flex-1 items-center justify-center overflow-hidden px-4 py-16">
      <Horizon />
      <div className="relative w-full max-w-sm [perspective:1200px]">
        <Spotlight className="rounded-lg">
          <div className="surface-raised relative overflow-hidden rounded-lg border border-border-strong p-8 shadow-3 transition-transform duration-(--duration-slow) ease-out [transform:rotateX(2deg)] hover:[transform:rotateX(0deg)] motion-reduce:[transform:none]">
            <div aria-hidden className="absolute inset-x-0 top-0 h-px bg-gradient-to-r from-transparent via-accent/60 to-transparent" />
            <div className="flex items-center gap-2.5">
              <span aria-hidden className="size-3.5 rotate-45 rounded-[3px] bg-accent shadow-glow-accent" />
              <span className="text-base font-semibold tracking-tight">OpsPilot</span>
            </div>
            <h1 className="mt-8 text-2xl font-semibold tracking-tight">Sign in</h1>
            <p className="mt-2 text-sm text-fg-secondary">
              Use your organization&apos;s single sign-on to open the command center.
            </p>
            <Suspense fallback={<div className="skeleton mt-8 h-11 rounded-sm" />}>
              <LoginPanel />
            </Suspense>
            <p className="mt-6 text-center font-mono text-[11px] text-fg-muted">
              Detect · Investigate · Remediate safely
            </p>
          </div>
        </Spotlight>
      </div>
    </main>
  );
}
