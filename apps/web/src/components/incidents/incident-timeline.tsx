import type { components } from "@opspilot/api-client/schema";

type Event = components["schemas"]["EventOut"];

const time = new Intl.DateTimeFormat(undefined, { dateStyle: "medium", timeStyle: "medium" });

const ACTOR: Record<Event["actor_type"], string> = { user: "User", agent: "Agent", system: "System" };

/** Depth-stacked timeline (plan §16.1): newest entry sits on top, raised. */
export function IncidentTimeline({ events }: { events: Event[] }) {
  if (events.length === 0) {
    return <p className="px-5 py-8 text-center text-sm text-fg-muted">No timeline events yet.</p>;
  }
  const newestFirst = [...events].reverse();
  return (
    <ol aria-label="Timeline" className="flex flex-col gap-3 p-5">
      {newestFirst.map((event, index) => (
        <li
          key={event.id}
          className={`relative rounded-card border border-border px-4 py-3 ${
            index === 0 ? "bg-surface-3 shadow-2" : "bg-surface-2 shadow-1"
          }`}
        >
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
        </li>
      ))}
    </ol>
  );
}
