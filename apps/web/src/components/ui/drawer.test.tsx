import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { useState } from "react";
import { beforeAll, describe, expect, it, vi } from "vitest";

import { Drawer } from "./drawer";

beforeAll(() => {
  // jsdom has no <dialog> behaviour; emulate the parts the drawer relies on.
  HTMLDialogElement.prototype.showModal = function (this: HTMLDialogElement) {
    this.open = true;
  };
  HTMLDialogElement.prototype.close = function (this: HTMLDialogElement) {
    this.open = false;
    this.dispatchEvent(new Event("close"));
  };
});

function Harness({ onClose }: { onClose?: () => void }) {
  const [open, setOpen] = useState(false);
  return (
    <>
      <button onClick={() => setOpen(true)}>Open details</button>
      <Drawer
        open={open}
        title="Service details"
        onClose={() => {
          setOpen(false);
          onClose?.();
        }}
      >
        <input aria-label="Filter services" />
      </Drawer>
    </>
  );
}

describe("Drawer", () => {
  it("opens as a labelled dialog and moves focus inside", async () => {
    const user = userEvent.setup();
    render(<Harness />);

    await user.click(screen.getByRole("button", { name: "Open details" }));

    const dialog = screen.getByRole("dialog", { name: "Service details" });
    expect(dialog).toHaveAttribute("open");
    expect(dialog).toContainElement(document.activeElement as HTMLElement);
  });

  it("closes from the close button and returns focus", async () => {
    const user = userEvent.setup();
    const onClose = vi.fn();
    render(<Harness onClose={onClose} />);
    const trigger = screen.getByRole("button", { name: "Open details" });

    await user.click(trigger);
    await user.click(screen.getByRole("button", { name: "Close" }));

    expect(onClose).toHaveBeenCalledOnce();
    expect(screen.queryByRole("textbox", { name: "Filter services" })).not.toBeInTheDocument();
    expect(trigger).toHaveFocus();
  });
});
