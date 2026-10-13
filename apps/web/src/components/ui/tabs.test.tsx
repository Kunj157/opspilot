import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it } from "vitest";

import { Tabs } from "./tabs";

const items = [
  { id: "metrics", label: "Metrics", content: <p>Metric panel</p> },
  { id: "logs", label: "Logs", content: <p>Log panel</p> },
  { id: "traces", label: "Traces", content: <p>Trace panel</p> },
];

describe("Tabs", () => {
  it("shows the first panel and links tabs to panels", () => {
    render(<Tabs label="Signals" items={items} />);

    const tab = screen.getByRole("tab", { name: "Metrics" });
    expect(tab).toHaveAttribute("aria-selected", "true");
    expect(screen.getByRole("tabpanel", { name: "Metrics" })).toHaveTextContent("Metric panel");
    expect(screen.queryByText("Log panel")).not.toBeInTheDocument();
  });

  it("moves with arrow keys, wraps, and supports Home and End", async () => {
    const user = userEvent.setup();
    render(<Tabs label="Signals" items={items} />);

    await user.click(screen.getByRole("tab", { name: "Metrics" }));
    await user.keyboard("{ArrowRight}");
    expect(screen.getByRole("tab", { name: "Logs" })).toHaveFocus();
    expect(screen.getByRole("tabpanel")).toHaveTextContent("Log panel");

    await user.keyboard("{ArrowLeft}{ArrowLeft}");
    expect(screen.getByRole("tab", { name: "Traces" })).toHaveFocus();

    await user.keyboard("{Home}");
    expect(screen.getByRole("tab", { name: "Metrics" })).toHaveAttribute("aria-selected", "true");
    await user.keyboard("{End}");
    expect(screen.getByRole("tab", { name: "Traces" })).toHaveAttribute("aria-selected", "true");
  });

  it("keeps only the selected tab in the tab order", () => {
    render(<Tabs label="Signals" items={items} />);

    expect(screen.getAllByRole("tab").map((t) => t.tabIndex)).toEqual([0, -1, -1]);
  });
});
