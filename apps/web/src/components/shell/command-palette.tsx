"use client";

import { createApiClient, type Permission } from "@opspilot/api-client";
import { useQuery } from "@tanstack/react-query";
import { useRouter } from "next/navigation";
import { type KeyboardEvent, useEffect, useId, useMemo, useRef, useState } from "react";

import { icons } from "@/components/icons";
import { ActiveHighlight } from "@/components/motion/animated-background";
import { MotionScope } from "@/components/motion/motion-provider";
import { SERVICES_KEY } from "@/components/services/service-catalog";
import { Kbd } from "@/components/ui/empty-state";
import { ACTIVE_STATUSES } from "@/lib/incident-filters";
import { filterItems, type PaletteItem } from "@/lib/palette-match";

import { NAV_ITEMS } from "./nav-items";

type Command = PaletteItem & { run: () => void };

const GROUPS = ["Go to", "Actions", "Incidents", "Services"] as const;

function api() {
  return createApiClient(window.location.origin);
}

/** Everything the palette can do for this user, built from what the API lets them see. */
function useCommands(navigate: (href: string) => void): Command[] {
  const me = useQuery({
    queryKey: ["me"],
    queryFn: async ({ signal }) => {
      const { data } = await api().GET("/api/v1/me", { signal });
      if (!data) throw new Error("me unavailable");
      return data;
    },
    staleTime: 60_000,
  });
  const can = (permission: Permission) => me.data?.permissions.includes(permission) ?? false;

  const incidents = useQuery({
    queryKey: ["palette", "incidents"],
    enabled: can("view_incidents"),
    queryFn: async ({ signal }) => {
      const { data } = await api().GET("/api/v1/incidents", {
        params: { query: { status: ACTIVE_STATUSES, limit: 20 } },
        signal,
      });
      if (!data) throw new Error("incidents unavailable");
      return data.items;
    },
  });
  const services = useQuery({
    queryKey: SERVICES_KEY,
    enabled: can("view_services"),
    queryFn: async ({ signal }) => {
      const { data } = await api().GET("/api/v1/services", { signal });
      if (!data) throw new Error("services unavailable");
      return data.items;
    },
  });

  const go = (href: string) => () => navigate(href);
  return [
    ...NAV_ITEMS.filter((item) => !item.permission || can(item.permission)).map((item) => ({
      id: `nav:${item.href}`,
      group: "Go to",
      label: item.label,
      run: go(item.href),
    })),
    ...(can("manage_incidents")
      ? [{ id: "action:new-incident", group: "Actions", label: "New incident", keywords: "create open declare", run: go("/incidents?new=1") }]
      : []),
    {
      id: "action:sign-out",
      group: "Actions",
      label: "Sign out",
      keywords: "log out logout",
      run: () => (document.getElementById("palette-sign-out") as HTMLFormElement | null)?.requestSubmit(),
    },
    ...(incidents.data ?? []).map((incident) => ({
      id: `incident:${incident.id}`,
      group: "Incidents",
      label: incident.title,
      keywords: `${incident.severity} ${incident.status.toLowerCase().replace("_", " ")}`,
      hint: incident.severity,
      run: go(`/incidents/${incident.id}`),
    })),
    ...(services.data ?? []).map((service) => ({
      id: `service:${service.id}`,
      group: "Services",
      label: service.name,
      keywords: service.slug,
      hint: service.health_status,
      run: go(`/services/${service.id}`),
    })),
    ...(services.data ?? []).map((service) => ({
      id: `map:${service.id}`,
      group: "Services",
      label: `Show ${service.name} on the map`,
      keywords: `${service.slug} topology focus`,
      run: go(`/?focus=${service.id}`),
    })),
  ];
}

/**
 * ⌘K command palette: jump to any section, open an incident or service, or run
 * an action. A modal <dialog> (focus trap, Esc, focus restore) around a
 * WAI-ARIA combobox and grouped listbox.
 */
export default function CommandPalette({ open, onClose }: { open: boolean; onClose: () => void }) {
  const router = useRouter();
  const dialog = useRef<HTMLDialogElement>(null);
  const list = useRef<HTMLDivElement>(null);
  const base = useId();
  const [query, setQuery] = useState("");
  const [active, setActive] = useState(0);
  const commands = useCommands((href) => router.push(href));

  const results = useMemo(() => {
    const matched = filterItems(commands, query);
    return GROUPS.flatMap((group) => matched.filter((c) => c.group === group).slice(0, query ? 8 : 6));
  }, [commands, query]);
  const current = Math.min(active, Math.max(0, results.length - 1));
  const optionId = (index: number) => `${base}-option-${index}`;

  useEffect(() => {
    const node = dialog.current;
    if (!node) return;
    if (open && !node.open) node.showModal();
    if (!open && node.open) node.close();
  }, [open]);

  useEffect(() => {
    list.current?.querySelector(`[id="${optionId(current)}"]`)?.scrollIntoView({ block: "nearest" });
    // eslint-disable-next-line react-hooks/exhaustive-deps -- optionId is derived from a stable id
  }, [current]);

  function run(command: Command | undefined) {
    if (!command) return;
    onClose();
    setQuery("");
    setActive(0);
    command.run();
  }

  function onKeyDown(event: KeyboardEvent<HTMLInputElement>) {
    const last = results.length - 1;
    const moves: Record<string, number> = {
      ArrowDown: current >= last ? 0 : current + 1,
      ArrowUp: current <= 0 ? last : current - 1,
      Home: 0,
      End: last,
    };
    if (event.key in moves && results.length > 0) {
      event.preventDefault();
      setActive(moves[event.key]);
    } else if (event.key === "Enter") {
      event.preventDefault();
      run(results[current]);
    }
  }

  const positions = new Map(results.map((command, i) => [command.id, i]));
  return (
    <dialog
      ref={dialog}
      aria-label="Command palette"
      onClose={onClose}
      onClick={(event) => event.target === dialog.current && onClose()}
      className="palette-dialog mx-auto mt-[12vh] w-[min(36rem,calc(100vw-2rem))] overflow-hidden rounded-lg border border-border-strong bg-surface-glass p-0 text-fg shadow-3 backdrop-blur-xl backdrop:bg-black/50 backdrop:backdrop-blur-[2px]"
    >
      {open && (
        <MotionScope>
          <div className="flex items-center gap-3 border-b border-border px-4 transition-colors focus-within:border-accent/60">
            <icons.search className="shrink-0 text-fg-muted" />
            <input
              autoFocus
              role="combobox"
              aria-expanded="true"
              aria-controls={`${base}-list`}
              aria-autocomplete="list"
              aria-activedescendant={results.length ? optionId(current) : undefined}
              aria-label="Search commands"
              placeholder="Search incidents, services, or actions…"
              value={query}
              onChange={(e) => {
                setQuery(e.target.value);
                setActive(0);
              }}
              onKeyDown={onKeyDown}
              className="h-12 flex-1 bg-transparent text-sm text-fg placeholder:text-fg-muted focus-visible:outline-none"
            />
            <Kbd>esc</Kbd>
          </div>
          <div ref={list} id={`${base}-list`} role="listbox" aria-label="Results" className="max-h-[min(24rem,60vh)] overflow-y-auto p-2">
            {results.length === 0 && <p className="px-3 py-8 text-center text-sm text-fg-muted">No matches for “{query}”.</p>}
            {GROUPS.map((group) => {
              const items = results.filter((c) => c.group === group);
              if (items.length === 0) return null;
              return (
                <div key={group} role="group" aria-labelledby={`${base}-${group.replace(" ", "-")}`} className="pb-1">
                  <p id={`${base}-${group.replace(" ", "-")}`} className="px-3 pt-2 pb-1 text-xs text-fg-muted">
                    {group}
                  </p>
                  {items.map((command) => {
                    const position = positions.get(command.id) ?? 0;
                    const selected = position === current;
                    return (
                      <div
                        key={command.id}
                        id={optionId(position)}
                        role="option"
                        aria-selected={selected}
                        onPointerMove={() => setActive(position)}
                        onClick={() => run(command)}
                        className={`relative isolate flex cursor-pointer items-center justify-between gap-3 rounded-sm px-3 py-2 text-sm ${
                          selected ? "text-fg" : "text-fg-secondary"
                        }`}
                      >
                        {selected && <ActiveHighlight layoutId={`${base}-highlight`} className="rounded-sm bg-accent-subtle" />}
                        <span className="truncate">{command.label}</span>
                        {command.hint && <span className="shrink-0 font-mono text-xs text-fg-muted">{command.hint}</span>}
                      </div>
                    );
                  })}
                </div>
              );
            })}
          </div>
          <div aria-hidden className="flex items-center gap-4 border-t border-border px-4 py-2 text-xs text-fg-muted">
            <span className="flex items-center gap-1">
              <Kbd>↑</Kbd>
              <Kbd>↓</Kbd> move
            </span>
            <span className="flex items-center gap-1">
              <Kbd>↵</Kbd> open
            </span>
          </div>
        </MotionScope>
      )}
      <form id="palette-sign-out" action="/auth/logout" method="post" hidden />
    </dialog>
  );
}
