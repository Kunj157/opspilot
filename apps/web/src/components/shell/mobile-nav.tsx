"use client";

import { type ReactNode, useRef, useState } from "react";

import { icons } from "@/components/icons";

import type { NavItem } from "./nav-items";
import { SidebarNav } from "./sidebar-nav";

/** Navigation drawer for narrow screens. A modal <dialog> traps focus and closes on Esc. */
export function MobileNav({ items, footer }: { items: NavItem[]; footer: ReactNode }) {
  const dialog = useRef<HTMLDialogElement>(null);
  // Content mounts only while open, so closed menus add no duplicate controls.
  const [open, setOpen] = useState(false);
  const close = () => dialog.current?.close();
  return (
    <>
      <button
        type="button"
        onClick={() => {
          setOpen(true);
          dialog.current?.showModal();
        }}
        aria-label="Open navigation"
        className="rounded-sm p-2 text-fg-secondary hover:bg-surface-2 hover:text-fg"
      >
        <icons.menu width={20} height={20} />
      </button>
      <dialog
        ref={dialog}
        aria-label="Navigation"
        onClose={() => setOpen(false)}
        className="m-0 h-full max-h-none w-72 max-w-[85vw] border-r border-border bg-surface-1 p-0 text-fg shadow-3 backdrop:bg-black/60"
      >
        {open && (
        <div className="flex h-full flex-col gap-6 p-4">
          <div className="flex items-center justify-between">
            <span className="text-sm font-semibold tracking-tight">OpsPilot</span>
            <button
              type="button"
              onClick={close}
              aria-label="Close navigation"
              className="rounded-sm p-2 text-fg-secondary hover:bg-surface-2 hover:text-fg"
            >
              <icons.close width={18} height={18} />
            </button>
          </div>
          <SidebarNav items={items} onNavigate={close} />
          <div className="mt-auto">{footer}</div>
        </div>
        )}
      </dialog>
    </>
  );
}
