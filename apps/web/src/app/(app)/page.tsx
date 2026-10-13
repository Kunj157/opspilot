import { CommandCenter } from "@/components/command-center";

export const metadata = { title: "Command center · OpsPilot" };

export default function CommandCenterPage() {
  return (
    <main className="w-full max-w-5xl flex-1 px-4 py-10 sm:px-8 sm:py-12">
      <p className="font-mono text-xs uppercase tracking-[0.18em] text-accent">Command center</p>
      <h1 className="mt-3 text-3xl font-semibold tracking-tight sm:text-4xl">Overview</h1>
      <p className="mt-3 max-w-xl text-fg-secondary">
        What needs attention right now across your services.
      </p>
      <div className="mt-10">
        <CommandCenter />
      </div>
    </main>
  );
}
