"use client";

import { type KeyboardEvent, type ReactNode, useId, useRef, useState } from "react";

import { ActiveHighlight } from "@/components/motion/animated-background";
import { MotionScope } from "@/components/motion/motion-provider";
import { TransitionPanel } from "@/components/motion/transition-panel";

export type TabItem = { id: string; label: string; content: ReactNode };

/** WAI-ARIA tabs: arrow keys move and select, Home/End jump, one tab stop. */
export function Tabs({ label, items }: { label: string; items: TabItem[] }) {
  const [selected, setSelected] = useState(items[0]?.id);
  const [direction, setDirection] = useState<1 | -1>(1);
  const base = useId();
  const tabs = useRef<(HTMLButtonElement | null)[]>([]);
  const current = items.findIndex((item) => item.id === selected);

  function select(index: number) {
    const next = (index + items.length) % items.length;
    choose(next);
    tabs.current[next]?.focus();
  }

  function choose(index: number) {
    setDirection(index >= current ? 1 : -1);
    setSelected(items[index].id);
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
    <MotionScope>
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
              onClick={() => choose(index)}
              className={`relative isolate -mb-px px-3 py-2 text-sm transition-colors duration-(--duration-instant) ${
                active ? "text-fg" : "text-fg-secondary hover:text-fg"
              }`}
            >
              {/* The Iris underline slides to the selected tab. */}
              {active && <ActiveHighlight layoutId={`${base}-indicator`} className="top-auto h-0.5 rounded-full bg-accent" />}
              {item.label}
            </button>
          );
        })}
      </div>
      {items
        .filter((item) => item.id === selected)
        .map((item) => (
          <TransitionPanel key="panel" activeKey={item.id} direction={direction}>
            <div role="tabpanel" id={`${base}-panel-${item.id}`} aria-labelledby={`${base}-tab-${item.id}`} tabIndex={0} className="pt-4">
              {item.content}
            </div>
          </TransitionPanel>
        ))}
    </MotionScope>
  );
}
