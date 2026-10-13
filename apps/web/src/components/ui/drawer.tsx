"use client";

import { type ReactNode, useEffect, useRef } from "react";

import { icons } from "@/components/icons";

/**
 * Glass side panel on the native modal <dialog>: the browser traps focus,
 * makes the page inert, closes on Escape, and restores focus on close.
 */
export function Drawer({
  open,
  title,
  onClose,
  children,
}: {
  open: boolean;
  title: string;
  onClose: () => void;
  children: ReactNode;
}) {
  const dialog = useRef<HTMLDialogElement>(null);
  const opener = useRef<Element | null>(null);

  useEffect(() => {
    const node = dialog.current;
    if (!node) return;
    if (open && !node.open) {
      opener.current = document.activeElement;
      node.showModal();
      node.querySelector<HTMLElement>("button, a[href], input, select, textarea")?.focus();
    }
    if (!open && node.open) node.close();
    if (!open && opener.current instanceof HTMLElement) {
      opener.current.focus();
      opener.current = null;
    }
  }, [open]);

  return (
    <dialog
      ref={dialog}
      aria-label={title}
      onClose={() => open && onClose()}
      className="fixed inset-y-0 right-0 left-auto m-0 h-dvh max-h-none w-[min(28rem,100vw)] border-l border-border bg-surface-glass p-0 text-fg shadow-3 backdrop-blur-md backdrop:bg-black/40"
    >
      {open && (
        <div className="flex h-full flex-col">
          <div className="flex items-center justify-between gap-4 border-b border-border px-5 py-4">
            <h2 className="text-base font-semibold">{title}</h2>
            <button
              type="button"
              onClick={onClose}
              aria-label="Close"
              className="rounded-sm p-1.5 text-fg-secondary hover:bg-surface-3 hover:text-fg"
            >
              <icons.close />
            </button>
          </div>
          <div className="flex-1 overflow-y-auto p-5">{children}</div>
        </div>
      )}
    </dialog>
  );
}
