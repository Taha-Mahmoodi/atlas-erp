/**
 * Stock moves list (STRUCTURE §4): the append-only movement ledger. Filterable by type,
 * keyset-paginated (D-014); row click opens detail. Moves auto-created by other modules
 * (goods receipts, deliveries, production issues, quality holds) appear here too — their
 * `reference` field is a display-only breadcrumb to the driving document, not something this
 * UI creates.
 */

import { Link, useNavigate } from "@tanstack/react-router";
import { useState } from "react";

import { formatDate, formatQuantity } from "@/lib/format";
import { useMe } from "@/lib/session";
import { DataGrid, type DataGridColumn } from "@/components/DataGrid";
import { useItemOptions, useStockMoves } from "@/modules/inventory/hooks";
import type { MoveType, StockMove } from "@/modules/inventory/types";

export function StockMoveListPage() {
  const navigate = useNavigate();
  const me = useMe();
  const canCreate = (me.data?.permissions ?? []).includes("inventory.move.create");
  const items = useItemOptions();
  const [moveType, setMoveType] = useState<MoveType | "">("");

  const moves = useStockMoves(moveType ? { move_type: moveType } : {});
  const rows = moves.data?.pages.flatMap((page) => page.items) ?? [];

  const itemLabel = (itemId: string) => {
    const item = items.data?.items.find((i) => i.id === itemId);
    return item ? `${item.item_code} — ${item.name}` : itemId;
  };

  const columns: DataGridColumn<StockMove>[] = [
    { key: "move_number", header: "Move #", render: (row) => row.move_number, width: "150px" },
    { key: "move_type", header: "Type", render: (row) => row.move_type, width: "110px" },
    { key: "item_id", header: "Item", render: (row) => itemLabel(row.item_id) },
    { key: "quantity", header: "Quantity", align: "right", render: (row) => formatQuantity(row.quantity), width: "120px" },
    { key: "move_date", header: "Date", render: (row) => formatDate(row.move_date), width: "120px" },
    { key: "reference", header: "Reference", render: (row) => row.reference ?? "—", width: "150px" },
  ];

  return (
    <div>
      <div className="flex items-center justify-between">
        <h1 className="text-[22px] font-[650] tracking-[-0.01em] text-ink">Stock Moves</h1>
        {canCreate && (
          <Link
            to="/inventory/stock-moves/new"
            className="btn-ink"
          >
            New move
          </Link>
        )}
      </div>

      <div className="mt-4">
        <select
          value={moveType}
          onChange={(event) => setMoveType(event.target.value as MoveType | "")}
          className="rounded-control border border-line bg-surface px-2 py-1.5 text-sm text-ink"
        >
          <option value="">All types</option>
          <option value="RECEIPT">Receipt</option>
          <option value="ISSUE">Issue</option>
          <option value="TRANSFER">Transfer</option>
          <option value="ADJUSTMENT">Adjustment</option>
        </select>
      </div>

      <div className="mt-4">
        <DataGrid
          columns={columns}
          rows={rows}
          rowKey={(row) => row.id}
          onRowClick={(row) => void navigate({ to: "/inventory/stock-moves/$moveId", params: { moveId: row.id } })}
          loading={moves.isPending}
          emptyMessage="No stock moves yet."
          hasMore={moves.hasNextPage}
          onLoadMore={() => void moves.fetchNextPage()}
          loadingMore={moves.isFetchingNextPage}
          label="Stock moves"
        />
      </div>
    </div>
  );
}
