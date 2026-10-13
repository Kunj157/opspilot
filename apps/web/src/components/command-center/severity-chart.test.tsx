import { render, screen, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it } from "vitest";

import { niceMax, SeverityChart } from "./severity-chart";

const day = (date: string, critical = 0, high = 0, medium = 0, low = 0) => ({ date, critical, high, medium, low });
const daily = [day("2026-10-11"), day("2026-10-12", 2, 1, 0, 3), day("2026-10-13", 1, 0, 2, 0)];

describe("niceMax", () => {
  it.each([
    [0, 4],
    [3, 4],
    [5, 6],
    [9, 10],
    [11, 12],
    [17, 20],
    [43, 50],
  ])("rounds %s up to %s", (value, expected) => {
    expect(niceMax(value)).toBe(expected);
  });
});

describe("SeverityChart", () => {
  it("names every severity in a legend", () => {
    render(<SeverityChart daily={daily} />);

    const legend = screen.getByRole("list", { name: "Legend" });
    expect(within(legend).getAllByRole("listitem").map((li) => li.textContent)).toEqual([
      "Critical",
      "High",
      "Medium",
      "Low",
    ]);
  });

  it("draws one stacked column per day with a segment per non-zero severity", () => {
    render(<SeverityChart daily={daily} />);

    const chart = screen.getByRole("img", { name: /incidents started per day/i });
    expect(chart.querySelectorAll("[data-day]")).toHaveLength(3);
    expect(chart.querySelectorAll('[data-day="2026-10-12"] [data-severity]')).toHaveLength(3);
    expect(chart.querySelectorAll('[data-day="2026-10-11"] [data-severity]')).toHaveLength(0);
  });

  it("shows the day's breakdown on hover", async () => {
    const user = userEvent.setup();
    render(<SeverityChart daily={daily} />);

    await user.hover(screen.getByRole("img").querySelector('[data-day="2026-10-12"] [data-hit]')!);

    const tip = screen.getByRole("tooltip");
    expect(tip).toHaveTextContent("6 incidents");
    expect(tip).toHaveTextContent("Critical2");
  });

  it("offers the same numbers as a table", async () => {
    const user = userEvent.setup();
    render(<SeverityChart daily={daily} />);

    await user.click(screen.getByRole("button", { name: "Show table" }));

    const rows = within(screen.getByRole("table")).getAllByRole("row");
    expect(rows).toHaveLength(4);
    expect(rows[2]).toHaveTextContent(/2\s*1\s*0\s*3\s*6/);
  });
});
