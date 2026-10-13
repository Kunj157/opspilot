import type { StreamState } from "@/lib/use-incident-stream";

const LABEL: Record<StreamState, string> = {
  connecting: "Connecting…",
  live: "Live",
  reconnecting: "Reconnecting…",
};

/** Connection state of a live stream, as text with a dot (never colour alone). */
export function LiveIndicator({ state }: { state: StreamState }) {
  return (
    <span role="status" className="inline-flex items-center gap-1.5 font-mono text-xs text-fg-secondary">
      <span
        aria-hidden
        className={`size-1.5 rounded-full ${state === "live" ? "bg-healthy" : "animate-pulse bg-degraded"}`}
      />
      {LABEL[state]}
    </span>
  );
}
