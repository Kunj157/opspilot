import { SystemStatus } from "@/components/system-status";

export default function Home() {
  return (
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
  );
}
