"use client";

import type { components } from "@opspilot/api-client/schema";
import { AnimatePresence, m } from "motion/react";
import { useState } from "react";

import { MotionScope } from "@/components/motion/motion-provider";
import { spring } from "@/lib/motion";

type Event = components["schemas"]["EventOut"];

const time = new Intl.DateTimeFormat(undefined, { dateStyle: "medium", timeStyle: "medium" });

const ACTOR: Record<Event["actor_type"], string> = { user: "User", agent: "Agent", system: "System" };
const DOT: Record<Event["actor_type"], string> = {
  user: "bg-fg-secondary",
  agent: "bg-accent shadow-glow-accent",
  system: "bg-fg-muted",
};

/**
 * Depth-stacked timeline on a rail (plan §16.1): the newest entry sits on top,
 * raised. Entries that stream in after the page loaded slide down into place
 * and briefly carry an Iris edge; the initial history renders still.
 */
export function IncidentTimeline({ events }: { events: Event[] }) {
  // Events present on first render are history, not news.
  const [seen] = useState(() => new Set(events.map((e) => e.id)));
  if (events.length === 0) {
    return <p className="px-5 py-8 text-center text-sm text-fg-muted">No timeline events yet.</p>;
  }
  const newestFirst = [...events].reverse();
  return (
    <MotionScope>
      <ol aria-label="Timeline" className="relative flex flex-col gap-3 p-5 pl-10">
        <span aria-hidden className="absolute top-7 bottom-7 left-[1.4rem] w-px bg-border-strong" />
        <AnimatePresence initial={false}>
          {newestFirst.map((event, index) => {
            const fresh = !seen.has(event.id);
            return (
              <m.li
                key={event.id}
                layout="position"
                initial={{ opacity: 0, y: -12 }}
                animate={{ opacity: 1, y: 0 }}
                transition={spring.smooth}
                className={`relative rounded-card border border-border px-4 py-3 ${
                  index === 0 ? "bg-surface-3 shadow-2" : "bg-surface-2 shadow-1"
                } ${fresh ? "just-arrived" : ""}`}
              >
                <span
                  aria-hidden
                  className={`absolute top-4 -left-[1.1rem] size-2 rounded-full ring-4 ring-surface-1 ${DOT[event.actor_type]}`}
                />
                <p className="flex flex-wrap items-baseline justify-between gap-x-3 gap-y-1">
                  <span className="text-sm font-medium">{event.title}</span>
                  <time dateTime={event.created_at} className="font-mono text-xs text-fg-muted">
                    {time.format(new Date(event.created_at))}
                  </time>
                </p>
                <p className="mt-1 text-xs text-fg-secondary">
                  <span className={event.actor_type === "agent" ? "text-accent" : undefined}>{ACTOR[event.actor_type]}</span>
                  {" · "}
                  <span className="font-mono">{event.event_type}</span>
                  {typeof event.metadata.reason === "string" && <> · {event.metadata.reason}</>}
                </p>
                {event.description && <p className="mt-2 text-sm text-fg-secondary">{event.description}</p>}
              </m.li>
            );
          })}
        </AnimatePresence>
      </ol>
    </MotionScope>
  );
}
