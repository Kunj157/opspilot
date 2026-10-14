import { act, render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, describe, expect, it, vi } from "vitest";

import ToastList from "./toast-list";
import { ToastProvider, useToast } from "./toast";

function Trigger({ tone }: { tone?: "success" | "error" }) {
  const toast = useToast();
  return <button onClick={() => toast("Incident resolved", tone)}>Notify</button>;
}

afterEach(() => {
  vi.useRealTimers();
});

describe("Toast", () => {
  it("announces messages politely and dismisses them", async () => {
    const user = userEvent.setup();
    render(
      <ToastProvider>
        <Trigger />
      </ToastProvider>,
    );

    await user.click(screen.getByRole("button", { name: "Notify" }));

    const region = screen.getByRole("region", { name: "Notifications" });
    expect(region).toHaveAttribute("aria-live", "polite");
    // The animated list loads with the first toast.
    await waitFor(() => expect(region).toHaveTextContent("Incident resolved"));
    await user.click(screen.getByRole("button", { name: "Dismiss" }));
    // It slides out first.
    await waitFor(() => expect(region).not.toHaveTextContent("Incident resolved"));
  });

  it("announces errors assertively", async () => {
    const user = userEvent.setup();
    render(
      <ToastProvider>
        <Trigger tone="error" />
      </ToastProvider>,
    );

    await user.click(screen.getByRole("button", { name: "Notify" }));

    const region = screen.getByRole("region", { name: "Error messages" });
    expect(region).toHaveAttribute("aria-live", "assertive");
    await waitFor(() => expect(region).toHaveTextContent("Incident resolved"));
  });

  it("expires after a few seconds", async () => {
    vi.useFakeTimers({ toFake: ["setTimeout", "clearTimeout"] });
    render(
      <ToastProvider>
        <Trigger />
      </ToastProvider>,
    );

    act(() => screen.getByRole("button", { name: "Notify" }).click());
    await vi.waitFor(() => expect(screen.getByRole("region", { name: "Notifications" })).toHaveTextContent("Incident resolved"));
    act(() => vi.advanceTimersByTime(6000));

    await vi.waitFor(() =>
      expect(screen.getByRole("region", { name: "Notifications" })).not.toHaveTextContent("Incident resolved"),
    );
  });

  it("marks the tone with a glyph, not colour alone", () => {
    render(
      <ToastList
        toasts={[
          { id: 1, message: "Saved", tone: "success" },
          { id: 2, message: "Failed", tone: "error" },
        ]}
        dismiss={() => {}}
        lifetime={5000}
      />,
    );
    expect(screen.getByText("Saved").previousElementSibling).toHaveTextContent("✓");
    expect(screen.getByText("Failed").previousElementSibling).toHaveTextContent("!");
  });
});
