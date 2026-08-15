/**
 * A check's lines, and the row that adds one while the check is still OPEN.
 *
 * Lines may only be added before the ticket fires (409 `hospitality.ticket_not_open` after) —
 * a fired line is already being cooked and already counted for depletion — so the add row simply
 * disappears once the kitchen has it.
 *
 * `unit_price` is caller-supplied and the staff service TRUSTS it, which is why it is an editable
 * field here rather than a hidden one. It is prefilled from the menu's resolved price so a server
 * types nothing in the ordinary case; a dish the price list does not cover today prefills empty
 * and has to be priced deliberately, which is the honest behaviour — the alternative is selling
 * it for zero. (The website surface resolves price server-side instead, because that caller is
 * untrusted. There is no staff-side equivalent endpoint: `/sales/price-quote` needs a customer id
 * and a walk-in table has none.)
 *
 * The menu read is `hospitality.menu.read`, which a server may not hold — so it degrades to raw
 * item ids and a note rather than taking the whole check down (see `useMenu`'s `throwOnError`).
 */

import { useState } from "react";

import { getErrorMessage } from "@/lib/apiClient";
import { formatMoney, formatQuantity } from "@/lib/format";
import { useAddTicketLines, useMenu } from "@/modules/hospitality/hooks";
import type { OrderTicketLine } from "@/modules/hospitality/types";

const CONTROL =
  "w-full rounded-control border border-line bg-surface px-2 py-1.5 text-sm text-ink transition-colors duration-150 hover:border-ink-faint";

export function TicketLinesEditor({
  ticketId,
  lines,
  currencyCode,
  editable,
}: {
  ticketId: string;
  lines: OrderTicketLine[];
  currencyCode: string;
  /** OPEN and the caller holds `ticket.manage` — anything else is a read-only lines table. */
  editable: boolean;
}) {
  const menu = useMenu();
  const addLines = useAddTicketLines(ticketId);
  const [itemId, setItemId] = useState("");
  const [quantity, setQuantity] = useState("1");
  const [unitPrice, setUnitPrice] = useState("");
  const [seat, setSeat] = useState("");
  const [notes, setNotes] = useState("");
  const [error, setError] = useState<string | null>(null);

  const itemLabel = (id: string) => {
    const item = menu.data?.items.find((entry) => entry.item_id === id);
    return item ? `${item.item_code} — ${item.name}` : id;
  };

  const pickItem = (id: string) => {
    setItemId(id);
    setUnitPrice(menu.data?.items.find((entry) => entry.item_id === id)?.price ?? "");
  };

  const add = async () => {
    setError(null);
    if (!itemId || !quantity || !unitPrice) {
      setError("Pick a dish and give it a quantity and a price.");
      return;
    }
    try {
      await addLines.mutateAsync({
        lines: [
          {
            item_id: itemId,
            quantity,
            unit_price: unitPrice,
            seat_number: seat ? Number(seat) : null,
            notes: notes || null,
          },
        ],
      });
      setItemId("");
      setQuantity("1");
      setUnitPrice("");
      setSeat("");
      setNotes("");
    } catch (caught) {
      setError(getErrorMessage(caught, "Unable to add the dish."));
    }
  };

  return (
    <div className="mt-6">
      <h2 className="mb-3.5 mono-caps text-ink-muted">Lines</h2>
      {error && (
        <p role="alert" className="mb-3 rounded-control bg-danger-tint px-3 py-2 text-xs text-danger">
          {error}
        </p>
      )}
      {menu.isError && (
        <p className="mb-3 text-xs text-ink-muted">
          Dishes show as ids: this account cannot read the menu (hospitality.menu.read).
        </p>
      )}
      <table className="w-full border-collapse text-[13px]">
        <thead>
          <tr className="border-b border-line text-left mono-caps text-ink-muted">
            <th className="py-2 pr-2">Seat</th>
            <th className="py-2 pr-2">Dish</th>
            <th className="py-2 pr-2">Note</th>
            <th className="py-2 pr-2 text-right">Qty</th>
            <th className="py-2 pr-2 text-right">Unit price</th>
            <th className="py-2 pr-2 text-right">Amount</th>
          </tr>
        </thead>
        <tbody>
          {lines.length === 0 && (
            <tr>
              <td colSpan={6} className="py-6 text-center text-[13px] text-ink-muted">
                Nothing ordered yet.
              </td>
            </tr>
          )}
          {lines.map((line) => (
            <tr key={line.id} className="border-b border-line last:border-b-0">
              <td className="py-1.5 pr-2 tabular-nums text-ink-muted">{line.seat_number ?? "—"}</td>
              <td className="py-1.5 pr-2 text-ink">{itemLabel(line.item_id)}</td>
              <td className="py-1.5 pr-2 text-ink-muted">{line.notes ?? "—"}</td>
              <td className="py-1.5 pr-2 text-right tabular-nums">{formatQuantity(line.quantity)}</td>
              <td className="py-1.5 pr-2 text-right tabular-nums">
                {formatMoney(line.unit_price, currencyCode)}
              </td>
              <td className="py-1.5 pr-2 text-right tabular-nums">
                {formatMoney(line.line_amount, currencyCode)}
              </td>
            </tr>
          ))}
        </tbody>
      </table>

      {editable && (
        <div className="mt-4 grid grid-cols-2 items-end gap-3 rounded-card border border-line bg-panel p-3 sm:grid-cols-12">
          <div className="sm:col-span-1">
            <label htmlFor="line-seat" className="mb-1 block text-xs font-medium text-ink-muted">
              Seat
            </label>
            <input
              id="line-seat"
              type="number"
              min={1}
              value={seat}
              onChange={(event) => setSeat(event.target.value)}
              className={`${CONTROL} tabular-nums`}
            />
          </div>
          <div className="sm:col-span-4">
            <label htmlFor="line-item" className="mb-1 block text-xs font-medium text-ink-muted">
              Dish
            </label>
            <select
              id="line-item"
              value={itemId}
              onChange={(event) => pickItem(event.target.value)}
              className={CONTROL}
            >
              <option value="">Select…</option>
              {(menu.data?.items ?? []).map((item) => (
                <option key={item.item_id} value={item.item_id}>
                  {item.item_code} — {item.name}
                </option>
              ))}
            </select>
          </div>
          <div className="sm:col-span-3">
            <label htmlFor="line-notes" className="mb-1 block text-xs font-medium text-ink-muted">
              Note
            </label>
            <input
              id="line-notes"
              type="text"
              value={notes}
              onChange={(event) => setNotes(event.target.value)}
              placeholder="No onions"
              className={CONTROL}
            />
          </div>
          <div className="sm:col-span-1">
            <label htmlFor="line-qty" className="mb-1 block text-xs font-medium text-ink-muted">
              Qty
            </label>
            <input
              id="line-qty"
              type="number"
              step="0.000001"
              min={0}
              value={quantity}
              onChange={(event) => setQuantity(event.target.value)}
              className={`${CONTROL} text-right tabular-nums`}
            />
          </div>
          <div className="sm:col-span-2">
            <label htmlFor="line-price" className="mb-1 block text-xs font-medium text-ink-muted">
              Unit price
            </label>
            <input
              id="line-price"
              type="number"
              step="0.01"
              min={0}
              value={unitPrice}
              onChange={(event) => setUnitPrice(event.target.value)}
              className={`${CONTROL} text-right tabular-nums`}
            />
          </div>
          <div className="sm:col-span-1">
            <button
              type="button"
              onClick={() => void add()}
              disabled={addLines.isPending}
              className="btn-chip w-full"
            >
              {addLines.isPending ? "Adding…" : "Add"}
            </button>
          </div>
        </div>
      )}
    </div>
  );
}
