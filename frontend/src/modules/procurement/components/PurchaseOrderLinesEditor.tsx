/**
 * The line editor for a draft purchase order (module-specific composite, STRUCTURE §4).
 * Mirrors RequisitionLinesEditor/finance's BillLinesEditor, but unit_cost is required (a PO
 * is a firm commitment, unlike a requisition's optional estimate) and adds an optional tax
 * code per line.
 */

import type { Item, Uom } from "@/modules/inventory/types";
import type { PurchaseOrderLineCreate } from "@/modules/procurement/types";
import type { TaxCode } from "@/modules/finance/types";

export interface PurchaseOrderLinesEditorProps {
  lines: PurchaseOrderLineCreate[];
  items: Item[];
  uoms: Uom[];
  taxCodes: TaxCode[];
  onChange: (lines: PurchaseOrderLineCreate[]) => void;
}

function emptyLine(): PurchaseOrderLineCreate {
  return { item_id: "", quantity: "", uom_id: "", unit_cost: "" };
}

export function PurchaseOrderLinesEditor({ lines, items, uoms, taxCodes, onChange }: PurchaseOrderLinesEditorProps) {
  const updateLine = (index: number, patch: Partial<PurchaseOrderLineCreate>) => {
    onChange(lines.map((line, i) => (i === index ? { ...line, ...patch } : line)));
  };
  const removeLine = (index: number) => {
    onChange(lines.filter((_, i) => i !== index));
  };
  const total = lines.reduce((sum, line) => sum + (Number(line.quantity) || 0) * (Number(line.unit_cost) || 0), 0);

  return (
    <div>
      <table className="w-full border-collapse text-[13px]">
        <thead>
          <tr className="border-b border-line text-left mono-caps text-ink-muted">
            <th className="py-2 pr-2">Item</th>
            <th className="py-2 pr-2">Description</th>
            <th className="w-24 py-2 pr-2 text-right">Quantity</th>
            <th className="py-2 pr-2">UoM</th>
            <th className="w-28 py-2 pr-2 text-right">Unit cost</th>
            <th className="py-2 pr-2">Tax code</th>
            <th className="w-10 py-2" />
          </tr>
        </thead>
        <tbody>
          {lines.map((line, index) => (
            // eslint-disable-next-line react/no-array-index-key -- lines have no stable id pre-save
            <tr key={index} className="border-b border-line last:border-b-0">
              <td className="py-1.5 pr-2">
                <select
                  value={line.item_id}
                  onChange={(event) => updateLine(index, { item_id: event.target.value })}
                  className="w-full rounded-control border border-line bg-surface px-2 py-1 text-sm"
                >
                  <option value="">Select item</option>
                  {items.map((item) => (
                    <option key={item.id} value={item.id}>
                      {item.item_code} — {item.name}
                    </option>
                  ))}
                </select>
              </td>
              <td className="py-1.5 pr-2">
                <input
                  type="text"
                  value={line.description ?? ""}
                  onChange={(event) => updateLine(index, { description: event.target.value })}
                  className="w-full rounded-control border border-line bg-surface px-2 py-1 text-sm"
                />
              </td>
              <td className="py-1.5 pr-2">
                <input
                  type="number"
                  step="0.000001"
                  value={line.quantity}
                  onChange={(event) => updateLine(index, { quantity: event.target.value })}
                  className="w-full rounded-control border border-line bg-surface px-2 py-1 text-right text-sm tabular-nums"
                />
              </td>
              <td className="py-1.5 pr-2">
                <select
                  value={line.uom_id}
                  onChange={(event) => updateLine(index, { uom_id: event.target.value })}
                  className="w-full rounded-control border border-line bg-surface px-2 py-1 text-sm"
                >
                  <option value="">Select UoM</option>
                  {uoms.map((uom) => (
                    <option key={uom.id} value={uom.id}>
                      {uom.code}
                    </option>
                  ))}
                </select>
              </td>
              <td className="py-1.5 pr-2">
                <input
                  type="number"
                  step="0.01"
                  value={line.unit_cost}
                  onChange={(event) => updateLine(index, { unit_cost: event.target.value })}
                  className="w-full rounded-control border border-line bg-surface px-2 py-1 text-right text-sm tabular-nums"
                />
              </td>
              <td className="py-1.5 pr-2">
                <select
                  value={line.tax_code_id ?? ""}
                  onChange={(event) => updateLine(index, { tax_code_id: event.target.value || null })}
                  className="w-full rounded-control border border-line bg-surface px-2 py-1 text-sm"
                >
                  <option value="">None</option>
                  {taxCodes.map((tax) => (
                    <option key={tax.id} value={tax.id}>
                      {tax.code} ({tax.rate_percent}%)
                    </option>
                  ))}
                </select>
              </td>
              <td className="py-1.5 text-center">
                <button
                  type="button"
                  onClick={() => removeLine(index)}
                  aria-label="Remove line"
                  className="text-ink-faint transition-colors duration-150 hover:text-danger"
                >
                  ✕
                </button>
              </td>
            </tr>
          ))}
        </tbody>
      </table>
      <button
        type="button"
        onClick={() => onChange([...lines, emptyLine()])}
        className="mt-2 rounded-control px-2 py-1 text-sm font-medium text-primary transition-colors duration-150 hover:bg-primary-tint"
      >
        + Add line
      </button>
      <div className="mt-3 text-right text-sm tabular-nums text-ink-muted">
        Line total {total.toFixed(2)} (tax computed server-side)
      </div>
    </div>
  );
}
