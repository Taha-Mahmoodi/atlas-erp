/**
 * The line editor for a draft RFQ (module-specific composite, STRUCTURE §4). No price field —
 * RFQ lines carry no cost until record-quote fills in quoted_unit_cost per line, later in the
 * RFQ's lifecycle (SENT -> QUOTED), not at creation.
 */

import type { Item, Uom } from "@/modules/inventory/types";
import type { RfqLineCreate } from "@/modules/procurement/types";

export interface RfqLinesEditorProps {
  lines: RfqLineCreate[];
  items: Item[];
  uoms: Uom[];
  onChange: (lines: RfqLineCreate[]) => void;
}

function emptyLine(): RfqLineCreate {
  return { item_id: "", quantity: "", uom_id: "" };
}

export function RfqLinesEditor({ lines, items, uoms, onChange }: RfqLinesEditorProps) {
  const updateLine = (index: number, patch: Partial<RfqLineCreate>) => {
    onChange(lines.map((line, i) => (i === index ? { ...line, ...patch } : line)));
  };
  const removeLine = (index: number) => {
    onChange(lines.filter((_, i) => i !== index));
  };

  return (
    <div>
      <table className="w-full border-collapse text-[13px]">
        <thead>
          <tr className="border-b border-line text-left mono-caps text-ink-muted">
            <th className="py-2 pr-2">Item</th>
            <th className="py-2 pr-2">Description</th>
            <th className="w-24 py-2 pr-2 text-right">Quantity</th>
            <th className="py-2 pr-2">UoM</th>
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
    </div>
  );
}
