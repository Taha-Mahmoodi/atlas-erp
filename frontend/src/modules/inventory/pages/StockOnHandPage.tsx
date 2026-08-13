/**
 * Stock on-hand overview (STRUCTURE §4). `StockOnHandRead` is a maintained projection
 * (`inv_stock_quants`), not a live sum — an indexed point read updated transactionally with
 * every move; a bin that reaches exactly zero drops out of this list entirely rather than
 * showing a zero row.
 */

import { useState } from "react";

import { formatQuantity } from "@/lib/format";
import { DataGrid, type DataGridColumn } from "@/components/DataGrid";
import { useBinLookup, useItemLookup, useItemOptions, useStockOnHand } from "@/modules/inventory/hooks";
import type { StockOnHand } from "@/modules/inventory/types";

export function StockOnHandPage() {
  const [itemId, setItemId] = useState("");
  const items = useItemOptions();
  const itemLookup = useItemLookup();
  const binLookup = useBinLookup();

  const onHand = useStockOnHand(itemId ? { item_id: itemId } : {});
  const rows = onHand.data?.pages.flatMap((page) => page.items) ?? [];

  const itemLabel = (id: string) => {
    const item = itemLookup.data?.items.find((i) => i.id === id);
    return item ? `${item.item_code} — ${item.name}` : id;
  };
  const binLabel = (id: string) => {
    const bin = binLookup.data?.items.find((b) => b.id === id);
    return bin ? `${bin.code} — ${bin.name}` : id;
  };

  const columns: DataGridColumn<StockOnHand>[] = [
    { key: "item_id", header: "Item", render: (row) => itemLabel(row.item_id) },
    { key: "bin_id", header: "Bin", render: (row) => binLabel(row.bin_id) },
    { key: "lot_id", header: "Lot", render: (row) => row.lot_id ?? "—", width: "140px" },
    { key: "on_hand_qty", header: "On hand", align: "right", render: (row) => formatQuantity(row.on_hand_qty), width: "130px" },
  ];

  return (
    <div>
      <h1 className="text-xl font-semibold text-ink">Stock On-Hand</h1>

      <div className="mt-4">
        <select
          value={itemId}
          onChange={(event) => setItemId(event.target.value)}
          className="rounded-control border border-line bg-surface px-2 py-1.5 text-sm text-ink"
        >
          <option value="">All items</option>
          {(items.data?.items ?? []).map((item) => (
            <option key={item.id} value={item.id}>
              {item.item_code} — {item.name}
            </option>
          ))}
        </select>
      </div>

      <div className="mt-4">
        <DataGrid
          columns={columns}
          rows={rows}
          rowKey={(row) => `${row.item_id}:${row.bin_id}:${row.lot_id ?? ""}`}
          loading={onHand.isPending}
          emptyMessage="No stock on hand."
          hasMore={onHand.hasNextPage}
          onLoadMore={() => void onHand.fetchNextPage()}
          loadingMore={onHand.isFetchingNextPage}
          label="Stock on hand"
        />
      </div>
    </div>
  );
}
