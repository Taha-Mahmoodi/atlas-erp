/**
 * The ERP workhorse table (DESIGN.md): sortable headers with aria-sort, sticky header,
 * compact density, skeleton loading, teaching empty state, keyset "load more", and
 * row click with full keyboard operability. Knows NOTHING about ERP concepts —
 * data + callbacks only (STRUCTURE §4).
 */

import type { KeyboardEvent, ReactNode } from "react";

export interface DataGridColumn<T> {
  key: string;
  header: ReactNode;
  render: (row: T) => ReactNode;
  /** Right-align numbers so magnitudes line up (tabular-nums is applied for you). */
  align?: "left" | "right" | "center";
  width?: string;
  sortable?: boolean;
}

export interface DataGridSort {
  key: string;
  direction: "asc" | "desc";
}

export interface DataGridProps<T> {
  columns: DataGridColumn<T>[];
  rows: T[];
  rowKey: (row: T) => string;
  onRowClick?: (row: T) => void;
  /** Controlled sort: the grid renders state; the caller re-queries. */
  sort?: DataGridSort;
  onSortChange?: (sort: DataGridSort) => void;
  loading?: boolean;
  /** Shown when not loading and rows are empty. Teach the screen, don't just say "no data". */
  emptyMessage?: ReactNode;
  /** Keyset pagination (D-014): render a load-more affordance while a next cursor exists. */
  hasMore?: boolean;
  onLoadMore?: () => void;
  loadingMore?: boolean;
  density?: "compact" | "regular";
  /** Accessible table name. */
  label?: string;
}

const ALIGN = { left: "text-left", right: "text-right", center: "text-center" } as const;

function headerAria(sort: DataGridSort | undefined, key: string) {
  if (sort?.key !== key) return "none" as const;
  return sort.direction === "asc" ? ("ascending" as const) : ("descending" as const);
}

export function DataGrid<T>({
  columns,
  rows,
  rowKey,
  onRowClick,
  sort,
  onSortChange,
  loading = false,
  emptyMessage = "Nothing here yet.",
  hasMore = false,
  onLoadMore,
  loadingMore = false,
  density = "compact",
  label,
}: DataGridProps<T>) {
  const cellPad = density === "compact" ? "px-3 py-2" : "px-4 py-2.5";

  const toggleSort = (column: DataGridColumn<T>) => {
    if (!column.sortable || !onSortChange) return;
    const direction = sort?.key === column.key && sort.direction === "asc" ? "desc" : "asc";
    onSortChange({ key: column.key, direction });
  };

  const rowKeyDown = (event: KeyboardEvent, row: T) => {
    if (!onRowClick) return;
    if (event.key === "Enter" || event.key === " ") {
      event.preventDefault();
      onRowClick(row);
    }
  };

  return (
    <div className="overflow-x-auto rounded-card border border-line bg-surface shadow-card">
      <table className="w-full border-collapse text-[13px]" {...(label ? { "aria-label": label } : {})}>
        <thead>
          <tr className="sticky top-0 z-10 border-b border-line bg-panel">
            {columns.map((column) => (
              <th
                key={column.key}
                scope="col"
                aria-sort={headerAria(sort, column.key)}
                {...(column.width ? { style: { width: column.width } } : {})}
                className={`${cellPad} ${ALIGN[column.align ?? "left"]} text-[11px] font-semibold uppercase tracking-[0.02em] text-ink-muted`}
              >
                {column.sortable && onSortChange ? (
                  <button
                    type="button"
                    onClick={() => toggleSort(column)}
                    className="inline-flex items-center gap-1 rounded-[4px] hover:text-ink"
                  >
                    {column.header}
                    <span aria-hidden="true" className="text-[9px]">
                      {sort?.key === column.key ? (sort.direction === "asc" ? "▲" : "▼") : "△"}
                    </span>
                  </button>
                ) : (
                  column.header
                )}
              </th>
            ))}
          </tr>
        </thead>
        <tbody>
          {loading &&
            Array.from({ length: 5 }, (_, index) => (
              <tr key={`skeleton-${index}`} className="border-b border-line last:border-b-0">
                {columns.map((column) => (
                  <td key={column.key} className={cellPad}>
                    <span className="atlas-skeleton inline-block h-3.5 w-4/5">…</span>
                  </td>
                ))}
              </tr>
            ))}
          {!loading && rows.length === 0 && (
            <tr>
              <td colSpan={columns.length} className="px-4 py-10 text-center text-sm text-ink-muted">
                {emptyMessage}
              </td>
            </tr>
          )}
          {!loading &&
            rows.map((row) => (
              <tr
                key={rowKey(row)}
                {...(onRowClick
                  ? {
                      onClick: () => onRowClick(row),
                      onKeyDown: (event: KeyboardEvent) => rowKeyDown(event, row),
                      tabIndex: 0,
                      role: "button" as const,
                    }
                  : {})}
                className={`border-b border-line transition-colors duration-150 last:border-b-0 ${
                  onRowClick ? "cursor-pointer hover:bg-primary-tint/50" : ""
                }`}
              >
                {columns.map((column) => (
                  <td
                    key={column.key}
                    className={`${cellPad} ${ALIGN[column.align ?? "left"]} ${
                      column.align === "right" ? "tabular-nums" : ""
                    }`}
                  >
                    {column.render(row)}
                  </td>
                ))}
              </tr>
            ))}
        </tbody>
      </table>
      {hasMore && !loading && (
        <div className="border-t border-line bg-surface p-2 text-center">
          <button
            type="button"
            onClick={onLoadMore}
            disabled={loadingMore}
            className="rounded-control px-3 py-1.5 text-[13px] font-medium text-primary transition-colors duration-150 hover:bg-primary-tint disabled:cursor-not-allowed disabled:opacity-45"
          >
            {loadingMore ? "Loading…" : "Load more"}
          </button>
        </div>
      )}
    </div>
  );
}
