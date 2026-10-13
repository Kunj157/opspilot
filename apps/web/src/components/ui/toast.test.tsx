import { act, render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, describe, expect, it, vi } from "vitest";

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

    const region = screen.getByRole("status");
    expect(region).toHaveTextContent("Incident resolved");
    await user.click(screen.getByRole("button", { name: "Dismiss" }));
    expect(region).not.toHaveTextContent("Incident resolved");
  });

  it("announces errors assertively", async () => {
    const user = userEvent.setup();
    render(
      <ToastProvider>
        <Trigger tone="error" />
      </ToastProvider>,
    );

    await user.click(screen.getByRole("button", { name: "Notify" }));

    expect(screen.getByRole("alert")).toHaveTextContent("Incident resolved");
  });

  it("expires after a few seconds", () => {
    vi.useFakeTimers();
    render(
      <ToastProvider>
        <Trigger />
      </ToastProvider>,
    );

    act(() => screen.getByRole("button", { name: "Notify" }).click());
    expect(screen.getByRole("status")).toHaveTextContent("Incident resolved");
    act(() => vi.advanceTimersByTime(6000));

    expect(screen.getByRole("status")).not.toHaveTextContent("Incident resolved");
  });
});
