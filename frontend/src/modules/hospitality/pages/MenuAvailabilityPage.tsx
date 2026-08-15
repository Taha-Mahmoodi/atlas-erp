/**
 * The 86 board (STRUCTURE §4): every dish the kitchen has said something about, and nothing else.
 * A dish with no row here is available — that is the backend's contract, not a rendering shortcut,
 * which is why "back on the menu" is a Clear action that DELETES the row rather than a third state.
 *
 * `as_of` is displayed because the board is a snapshot: the endpoint stamps the single instant its
 * rows were resolved against, and a countdown can move between one read and the next.
 */

import { Link } from "@tanstack/react-router";
import { useState } from "react";

import { getErrorMessage } from "@/lib/apiClient";
import { formatDateTime, formatQuantity } from "@/lib/format";
import { useMe } from "@/lib/session";
import { DataGrid, type DataGridColumn } from "@/components/DataGrid";
import { StatusPill } from "@/components/StatusPill";
import { AvailabilityEditor } from "@/modules/hospitality/components/AvailabilityEditor";
import { useAvailabilityBoard, useClearAvailability, useMenu } from "@/modules/hospitality/hooks";
import type { MenuAvailability } from "@/modules/hospitality/types";

export function MenuAvailabilityPage() {
  const me = useMe();
  const canManage = (me.data?.permissions ?? []).includes("hospitality.menu.manage");

  const board = useAvailabilityBoard();
  const menu = useMenu();
  const clear = useClearAvailability();
  const [editing, setEditing] = useState<MenuAvailability | null>(null);
  const [creating, setCreating] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const rows = board.data?.pages.flatMap((page) => page.items) ?? [];
  const asOf = board.data?.pages[0]?.as_of;

  const itemLabel = (itemId: string) => {
    const item = menu.data?.items.find((entry) => entry.item_id === itemId);
    return item ? `${item.item_code} — ${item.name}` : itemId;
  };

  const clearRow = async (itemId: string) => {
    setError(null);
    try {
      await clear.mutateAsync(itemId);
      setEditing((current) => (current?.item_id === itemId ? null : current));
    } catch (caught) {
      setError(getErrorMessage(caught, "Unable to put the dish back on the menu."));
    }
  };

  const columns: DataGridColumn<MenuAvailability>[] = [
    { key: "item", header: "Dish", render: (row) => itemLabel(row.item_id) },
    {
      key: "state",
      header: "State",
      width: "130px",
      render: (row) => <StatusPill status={row.state} />,
    },
    {
      key: "remaining_qty",
      header: "Portions left",
      align: "right",
      width: "120px",
      render: (row) => (row.remaining_qty ? formatQuantity(row.remaining_qty) : "—"),
    },
    {
      key: "available_until",
      header: "In effect through",
      width: "180px",
      render: (row) => (row.available_until ? formatDateTime(row.available_until) : "—"),
    },
    {
      key: "source",
      header: "Set by",
      width: "110px",
      render: (row) => (row.source === "AUTO" ? "Countdown" : row.source === "MANUAL" ? "Staff" : "—"),
    },
    { key: "reason", header: "Reason", render: (row) => row.reason ?? "—" },
    // Explicit per-row buttons rather than a clickable row: a row that is itself a control cannot
    // also contain controls (nested interactive elements are not operable by keyboard or screen
    // reader), and 86ing is one of the two things a manager does here, not a detail view.
    ...(canManage
      ? [
          {
            key: "actions",
            header: "",
            width: "140px",
            render: (row: MenuAvailability) => (
              <span className="flex items-center gap-3">
                <button
                  type="button"
                  onClick={() => {
                    setCreating(false);
                    setEditing(row);
                  }}
                  className="text-[12.5px] font-medium text-primary hover:underline"
                >
                  Edit
                </button>
                <button
                  type="button"
                  onClick={() => void clearRow(row.item_id)}
                  disabled={clear.isPending}
                  className="text-[12.5px] font-medium text-primary hover:underline disabled:opacity-45"
                >
                  Clear
                </button>
              </span>
            ),
          },
        ]
      : []),
  ];

  return (
    <div>
      <header className="mb-6">
        <p className="text-[12px] text-ink-muted">
          <Link to="/hospitality" className="hover:underline">
            Hospitality
          </Link>{" "}
          / <span className="text-ink">Menu availability</span>
        </p>
        <div className="mt-1.5 flex items-start justify-between gap-4">
          <div>
            <h1 className="text-[22px] font-[650] tracking-[-0.01em] text-ink">Menu availability</h1>
            {asOf && (
              <p className="mt-1 text-[12px] text-ink-muted">As of {formatDateTime(asOf)}</p>
            )}
          </div>
          {canManage && (
            <button
              type="button"
              onClick={() => {
                setEditing(null);
                setCreating(true);
              }}
              className="btn-ink"
            >
              Set availability
            </button>
          )}
        </div>
      </header>

      {error && (
        <p role="alert" className="mt-4 rounded-control bg-danger-tint px-3 py-2 text-xs text-danger">
          {error}
        </p>
      )}

      {(creating || editing) && (
        <AvailabilityEditor
          {...(editing ? { existing: editing } : {})}
          onDone={() => {
            setCreating(false);
            setEditing(null);
          }}
        />
      )}

      <div className="mt-6">
        <DataGrid
          columns={columns}
          rows={rows}
          rowKey={(row) => row.item_id}
          loading={board.isPending}
          emptyMessage="Nothing is 86'd — every dish on the menu is available."
          hasMore={board.hasNextPage}
          onLoadMore={() => void board.fetchNextPage()}
          loadingMore={board.isFetchingNextPage}
          label="Menu availability"
        />
      </div>
    </div>
  );
}
