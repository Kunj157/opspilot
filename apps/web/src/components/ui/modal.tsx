"use client";

import { type ReactNode, useEffect, useRef } from "react";

import { icons } from "@/components/icons";

/** Accessible modal on the native <dialog>: focus trap, Esc to close, inert background. */
export function Modal({
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
  useEffect(() => {
    const node = dialog.current;
    if (!node) return;
    if (open && !node.open) node.showModal();
    if (!open && node.open) node.close();
  }, [open]);

  return (
    <dialog
      ref={dialog}
      aria-label={title}
      onClose={onClose}
      className="m-auto w-[min(36rem,calc(100vw-2rem))] rounded-lg border border-border bg-surface-2 p-0 text-fg shadow-3 backdrop:bg-black/60"
    >
      {open && (
        <div className="p-6">
          <div className="mb-5 flex items-center justify-between gap-4">
            <h2 className="text-lg font-semibold">{title}</h2>
            <button
              type="button"
              onClick={onClose}
              aria-label="Close"
              className="rounded-sm p-1.5 text-fg-secondary hover:bg-surface-3 hover:text-fg"
            >
              <icons.close />
            </button>
          </div>
          {children}
        </div>
      )}
    </dialog>
  );
}
