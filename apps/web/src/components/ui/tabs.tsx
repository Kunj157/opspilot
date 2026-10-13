"use client";

import { type KeyboardEvent, type ReactNode, useId, useRef, useState } from "react";

export type TabItem = { id: string; label: string; content: ReactNode };

/** WAI-ARIA tabs: arrow keys move and select, Home/End jump, one tab stop. */
export function Tabs({ label, items }: { label: string; items: TabItem[] }) {
  const [selected, setSelected] = useState(items[0]?.id);
  const base = useId();
  const tabs = useRef<(HTMLButtonElement | null)[]>([]);
  const current = items.findIndex((item) => item.id === selected);

  function select(index: number) {
    const next = (index + items.length) % items.length;
    setSelected(items[next].id);
    tabs.current[next]?.focus();
  }

  function onKeyDown(event: KeyboardEvent) {
    const moves: Record<string, number> = {
      ArrowRight: current + 1,
      ArrowLeft: current - 1,
      Home: 0,
      End: items.length - 1,
    };
    if (!(event.key in moves)) return;
    event.preventDefault();
    select(moves[event.key]);
  }

  return (
    <div>
      <div role="tablist" aria-label={label} onKeyDown={onKeyDown} className="flex gap-1 border-b border-border">
        {items.map((item, index) => {
          const active = item.id === selected;
          return (
            <button
              key={item.id}
              ref={(node) => {
                tabs.current[index] = node;
              }}
              type="button"
              role="tab"
              id={`${base}-tab-${item.id}`}
              aria-selected={active}
              aria-controls={`${base}-panel-${item.id}`}
              tabIndex={active ? 0 : -1}
              onClick={() => setSelected(item.id)}
              className={`-mb-px border-b-2 px-3 py-2 text-sm transition-colors duration-base ${
                active ? "border-accent text-fg" : "border-transparent text-fg-secondary hover:text-fg"
              }`}
            >
              {item.label}
            </button>
          );
        })}
      </div>
      {items
        .filter((item) => item.id === selected)
        .map((item) => (
          <div
            key={item.id}
            role="tabpanel"
            id={`${base}-panel-${item.id}`}
            aria-labelledby={`${base}-tab-${item.id}`}
            tabIndex={0}
            className="pt-4"
          >
            {item.content}
          </div>
        ))}
    </div>
  );
}
