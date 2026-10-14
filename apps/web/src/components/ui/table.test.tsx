import { render, screen, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it, vi } from "vitest";

import { type Column, DataTable, sortRows } from "./table";

type Row = { id: string; name: string; count: number };
const rows: Row[] = [
  { id: "a", name: "Checkout", count: 3 },
  { id: "b", name: "Auth", count: 10 },
  { id: "c", name: "Payments", count: 3 },
];
const columns: Column<Row>[] = [
  { id: "name", header: "Name", cell: (r) => <a href={`/s/${r.id}`}>{r.name}</a>, sortValue: (r) => r.name },
  { id: "count", header: "Incidents", cell: (r) => r.count, sortValue: (r) => r.count },
  { id: "note", header: "Note", cell: () => "—" },
];

const names = () =>
  within(screen.getByRole("table"))
    .getAllByRole("row")
    .slice(1)
    .map((r) => within(r).getAllByRole("cell")[0].textContent);

describe("sortRows", () => {
  it("sorts numbers and strings and keeps ties in their original order", () => {
    expect(sortRows(rows, columns, { id: "count", direction: "asc" }).map((r) => r.id)).toEqual(["a", "c", "b"]);
    expect(sortRows(rows, columns, { id: "count", direction: "desc" }).map((r) => r.id)).toEqual(["b", "a", "c"]);
    expect(sortRows(rows, columns, { id: "note", direction: "asc" })).toBe(rows);
  });
});

describe("DataTable", () => {
  it("keeps the incoming order until a column is sorted", () => {
    render(<DataTable caption="Services" columns={columns} rows={rows} rowKey={(r) => r.id} />);
    expect(screen.getByRole("table", { name: "Services" })).toBeInTheDocument();
    expect(names()).toEqual(["Checkout", "Auth", "Payments"]);
    expect(screen.getByRole("columnheader", { name: "Note" })).not.toHaveAttribute("aria-sort");
  });

  it("sorts by a column and toggles direction, announcing it with aria-sort", async () => {
    const user = userEvent.setup();
    render(<DataTable caption="Services" columns={columns} rows={rows} rowKey={(r) => r.id} />);
    const header = screen.getByRole("columnheader", { name: "Name" });

    await user.click(within(header).getByRole("button", { name: "Name" }));
    expect(header).toHaveAttribute("aria-sort", "ascending");
    expect(names()).toEqual(["Auth", "Checkout", "Payments"]);

    await user.click(within(header).getByRole("button", { name: "Name" }));
    expect(header).toHaveAttribute("aria-sort", "descending");
    expect(names()).toEqual(["Payments", "Checkout", "Auth"]);
  });

  it("follows the row link on a background click but not on a control", async () => {
    const user = userEvent.setup();
    const navigate = vi.fn();
    render(
      <DataTable
        caption="Services"
        columns={columns}
        rows={rows}
        rowKey={(r) => r.id}
        rowHref={(r) => `/s/${r.id}`}
        onNavigate={navigate}
      />,
    );
    await user.click(screen.getAllByRole("cell", { name: "—" })[1]);
    expect(navigate).toHaveBeenCalledWith("/s/b");

    navigate.mockClear();
    await user.click(screen.getByRole("columnheader", { name: "Incidents" }).querySelector("button")!);
    expect(navigate).not.toHaveBeenCalled();
  });
});
