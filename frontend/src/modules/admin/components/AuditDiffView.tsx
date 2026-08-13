/**
 * Renders an audit row's before/after diff (D-010) as one uniform field table. Shapes per
 * action: UPDATE = {field: {old, new}}; INSERT = {new: fullRow}; DELETE = {old: fullRow}.
 * All three normalize to (field, old, new) rows so the viewer needs no per-action layout.
 */

interface DiffRow {
  field: string;
  old: unknown;
  new: unknown;
}

function isOldNew(value: unknown): value is { old?: unknown; new?: unknown } {
  return (
    typeof value === "object" &&
    value !== null &&
    !Array.isArray(value) &&
    ("old" in value || "new" in value)
  );
}

function toRows(diff: Record<string, unknown>): DiffRow[] {
  // INSERT / DELETE: a single full-row snapshot under "new" / "old".
  if (isOldNew(diff) && Object.keys(diff).every((key) => key === "old" || key === "new")) {
    const oldRow = (diff.old ?? {}) as Record<string, unknown>;
    const newRow = (diff.new ?? {}) as Record<string, unknown>;
    const fields = [...new Set([...Object.keys(oldRow), ...Object.keys(newRow)])].sort();
    return fields.map((field) => ({ field, old: oldRow[field], new: newRow[field] }));
  }
  // UPDATE: {field: {old, new}} per changed field.
  return Object.entries(diff).map(([field, change]) => ({
    field,
    old: isOldNew(change) ? change.old : undefined,
    new: isOldNew(change) ? change.new : change,
  }));
}

function Value({ value }: { value: unknown }) {
  if (value === undefined || value === null) {
    return <span className="text-ink-faint">—</span>;
  }
  const text = typeof value === "string" ? value : JSON.stringify(value);
  return <span className="break-all text-ink">{text}</span>;
}

export function AuditDiffView({ diff }: { diff: Record<string, unknown> | null }) {
  if (diff === null || Object.keys(diff).length === 0) {
    return <p className="text-sm text-ink-muted">This entry recorded no field-level diff.</p>;
  }
  const rows = toRows(diff);
  return (
    <div className="overflow-x-auto">
      <table className="w-full text-sm">
        <thead>
          <tr className="border-b border-line text-left text-xs font-medium uppercase tracking-[0.04em] text-ink-muted">
            <th className="py-1.5 pr-4">Field</th>
            <th className="py-1.5 pr-4">Before</th>
            <th className="py-1.5">After</th>
          </tr>
        </thead>
        <tbody>
          {rows.map((row) => (
            <tr key={row.field} className="border-b border-line last:border-b-0 align-top">
              <td className="py-1.5 pr-4">
                <code className="text-xs text-ink">{row.field}</code>
              </td>
              <td className="py-1.5 pr-4">
                <Value value={row.old} />
              </td>
              <td className="py-1.5">
                <Value value={row.new} />
              </td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}
