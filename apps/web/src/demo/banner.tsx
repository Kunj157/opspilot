import Link from "next/link";

/** A strip across the top of the demo build so nobody mistakes the replay for a live system. */
export function DemoBanner() {
  if (process.env.NEXT_PUBLIC_DEMO !== "1") return null;
  return (
    <div className="relative z-50 flex flex-wrap items-center justify-center gap-x-3 gap-y-1 bg-accent px-4 py-1.5 text-center text-xs font-medium text-black">
      <span>Live demo: a recorded incident replays in your browser. No cluster, no model calls.</span>
      <Link
        className="font-semibold underline underline-offset-2"
        href="/incidents/00000000-0000-4000-8000-000000000001/"
      >
        Open the live incident and approve the rollback →
      </Link>
      <a className="underline underline-offset-2" href="https://github.com/Kunj157/opspilot">
        Source on GitHub
      </a>
    </div>
  );
}
