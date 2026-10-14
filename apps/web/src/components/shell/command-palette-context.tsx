"use client";

import dynamic from "next/dynamic";
import { createContext, type ReactNode, useCallback, useContext, useEffect, useMemo, useState } from "react";

import { icons } from "@/components/icons";
import { Kbd } from "@/components/ui/empty-state";

const load = () => import("./command-palette");
// Loaded on first use (or when the trigger is hovered or focused), never on the critical path.
const CommandPalette = dynamic(load, { ssr: false });

type Palette = { open: () => void };
const PaletteContext = createContext<Palette | null>(null);

/** Owns the palette's open state and the global ⌘K / Ctrl K shortcut. */
export function CommandPaletteProvider({ children }: { children: ReactNode }) {
  const [open, setOpen] = useState(false);
  const [used, setUsed] = useState(false);
  const show = useCallback(() => {
    setUsed(true);
    setOpen(true);
  }, []);

  useEffect(() => {
    function onKeyDown(event: KeyboardEvent) {
      if (event.key.toLowerCase() === "k" && (event.metaKey || event.ctrlKey) && !event.altKey) {
        event.preventDefault();
        setUsed(true);
        setOpen((current) => !current);
      }
    }
    window.addEventListener("keydown", onKeyDown);
    return () => window.removeEventListener("keydown", onKeyDown);
  }, []);

  const value = useMemo(() => ({ open: show }), [show]);
  return (
    <PaletteContext.Provider value={value}>
      {children}
      {used && <CommandPalette open={open} onClose={() => setOpen(false)} />}
    </PaletteContext.Provider>
  );
}

/** The search button in the top bar: a wide field on desktop, an icon on phones. */
export function CommandPaletteTrigger() {
  const palette = useContext(PaletteContext);
  if (!palette) throw new Error("CommandPaletteTrigger must be inside <CommandPaletteProvider>");
  const preload = () => void load();
  return (
    <button
      type="button"
      onClick={palette.open}
      onPointerEnter={preload}
      onFocus={preload}
      aria-keyshortcuts="Control+K Meta+K"
      className="group flex h-8 items-center gap-2 rounded-sm border border-border bg-surface-1/80 px-2.5 text-sm text-fg-muted shadow-edge transition-colors duration-(--duration-instant) hover:border-border-strong hover:text-fg-secondary sm:w-64"
    >
      <icons.search />
      <span className="sr-only sm:not-sr-only sm:flex-1 sm:text-left">Search or jump to…</span>
      <span aria-hidden className="hidden items-center gap-0.5 sm:inline-flex">
        <Kbd>⌘</Kbd>
        <Kbd>K</Kbd>
      </span>
    </button>
  );
}
