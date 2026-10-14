"use client";

import { type MouseEvent, type ReactNode, useState } from "react";

import { icons } from "@/components/icons";

export type SortDirection = "asc" | "desc";
export type Sort = { id: string; direction: SortDirection };

export type Column<T> = {
  id: string;
  header: ReactNode;
  cell: (row: T) => ReactNode;
  /** Makes the column sortable by this value. */
  sortValue?: (row: T) => string | number;
  /** Applied to the header and every cell, e.g. "hidden md:table-cell". */
  className?: string;
};

const ARIA_SORT = { asc: "ascending", desc: "descending" } as const;

export function sortRows<T>(rows: T[], columns: Column<T>[], sort: Sort | null): T[] {
  const column = sort && columns.find((c) => c.id === sort.id);
  if (!sort || !column?.sortValue) return rows;
  const value = column.sortValue;
  const factor = sort.direction === "asc" ? 1 : -1;
  // Stable: equal values keep their incoming (server) order.
  return rows
    .map((row, index) => ({ row, index }))
    .sort((a, b) => {
      const x = value(a.row);
      const y = value(b.row);
      const order = typeof x === "number" && typeof y === "number" ? x - y : String(x).localeCompare(String(y));
      return order * factor || a.index - b.index;
    })
    .map(({ row }) => row);
}

/** Clicks on the row background follow the row's link; clicks on controls keep their own meaning. */
function followRow(event: MouseEvent<HTMLTableRowElement>, href: string, navigate: (href: string) => void) {
  const target = event.target as HTMLElement;
  if (target.closest("a, button, input, select, textarea, label")) return;
  if (window.getSelection()?.toString()) return;
  navigate(href);
}

/**
 * The shared data table: sticky header, optional client-side sorting with
 * `aria-sort`, and rows that can follow a link on click. Keyboard and
 * screen-reader users reach the same destination through a link in a cell.
 */
export function DataTable<T>({
  caption,
  columns,
  rows,
  rowKey,
  defaultSort = null,
  rowHref,
  onNavigate,
  rowClassName,
}: {
  caption: string;
  columns: Column<T>[];
  rows: T[];
  rowKey: (row: T) => string;
  defaultSort?: Sort | null;
  rowHref?: (row: T) => string;
  onNavigate?: (href: string) => void;
  rowClassName?: (row: T) => string;
}) {
  const [sort, setSort] = useState<Sort | null>(defaultSort);
  const sorted = sortRows(rows, columns, sort);

  function toggle(id: string) {
    setSort((current) =>
      current?.id === id ? { id, direction: current.direction === "asc" ? "desc" : "asc" } : { id, direction: "asc" },
    );
  }

  return (
    <table className="w-full text-left text-sm">
      <caption className="sr-only">{caption}</caption>
      <thead className="text-xs text-fg-muted">
        <tr>
          {columns.map((column) => {
            const active = sort?.id === column.id;
            return (
              <th
                key={column.id}
                scope="col"
                aria-sort={active ? ARIA_SORT[sort.direction] : undefined}
                className={`sticky top-(--sticky-top) z-10 border-b border-border bg-surface-glass px-3 py-2.5 font-medium backdrop-blur-md first:pl-5 last:pr-5 ${column.className ?? ""}`}
              >
                {column.sortValue ? (
                  <button
                    type="button"
                    onClick={() => toggle(column.id)}
                    className={`-mx-1 inline-flex items-center gap-1 rounded-[6px] px-1 py-0.5 hover:text-fg ${active ? "text-fg" : ""}`}
                  >
                    {column.header}
                    <icons.sort
                      aria-hidden
                      data-direction={active ? sort.direction : "none"}
                      className={`size-3 transition-transform duration-(--duration-fast) ${active ? "opacity-100" : "opacity-40"} ${
                        active && sort.direction === "desc" ? "rotate-180" : ""
                      }`}
                    />
                  </button>
                ) : (
                  column.header
                )}
              </th>
            );
          })}
        </tr>
      </thead>
      <tbody className="divide-y divide-border">
        {sorted.map((row) => {
          const href = rowHref?.(row);
          return (
            <tr
              key={rowKey(row)}
              onClick={href && onNavigate ? (e) => followRow(e, href, onNavigate) : undefined}
              className={`transition-colors duration-(--duration-instant) hover:bg-surface-3/60 ${href ? "cursor-pointer" : ""} ${rowClassName?.(row) ?? ""}`}
            >
              {columns.map((column) => (
                <td key={column.id} className={`px-3 py-3 align-middle first:pl-5 last:pr-5 ${column.className ?? ""}`}>
                  {column.cell(row)}
                </td>
              ))}
            </tr>
          );
        })}
      </tbody>
    </table>
  );
}
