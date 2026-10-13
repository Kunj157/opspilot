import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it, vi } from "vitest";

import ErrorBoundary from "./error";

describe("app error boundary", () => {
  it("shows a recoverable message and retries", async () => {
    const reset = vi.fn();
    vi.spyOn(console, "error").mockImplementation(() => {});

    render(<ErrorBoundary error={new Error("kaboom")} reset={reset} />);
    await userEvent.click(screen.getByRole("button", { name: "Try again" }));

    expect(screen.getByRole("alert")).toHaveTextContent("Something went wrong");
    expect(screen.queryByText("kaboom")).not.toBeInTheDocument();
    expect(reset).toHaveBeenCalledOnce();
  });
});
