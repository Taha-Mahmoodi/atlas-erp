/**
 * Per-tenant number sequences, read-only (STRUCTURE §4, D-012). The backend deliberately
 * ships no adjust endpoint — mutating next_value would break the gapless guarantee — so
 * this page is a pure viewer.
 */

import { Link } from "@tanstack/react-router";

import { getErrorMessage } from "@/lib/apiClient";
import { DataGrid, type DataGridColumn } from "@/components/DataGrid";
import { useNumberSequences } from "@/modules/admin/hooks";
import type { NumberSequence, NumberSequenceCounter } from "@/modules/admin/types";

/** The number a claim in `counter`'s year would hand out next, e.g. `TKT-2026-000009`. */
function preview(sequence: NumberSequence, counter: NumberSequenceCounter): string {
  const padded = String(counter.next_value).padStart(sequence.padding, "0");
  return counter.year === null
    ? `${sequence.prefix}-${padded}`
    : `${sequence.prefix}-${counter.year}-${padded}`;
}

/** Every year the tenant has actually claimed in, newest first — a stray old year sitting next
 * to the live one is how a mis-dated document shows up here (issue #209). */
function counters(sequence: NumberSequence) {
  if (sequence.counters.length === 0) {
    return <span className="text-ink-muted">Nothing claimed yet</span>;
  }
  return (
    <div className="flex flex-wrap gap-x-4 gap-y-1 tabular-nums">
      {sequence.counters.map((counter) => (
        <span key={counter.year ?? "none"}>
          {preview(sequence, counter)}
          <span className="ml-1.5 text-ink-muted">#{counter.next_value}</span>
        </span>
      ))}
    </div>
  );
}

const COLUMNS: DataGridColumn<NumberSequence>[] = [
  { key: "name", header: "Sequence", render: (row) => row.name },
  { key: "prefix", header: "Prefix", render: (row) => row.prefix, width: "120px" },
  { key: "year_reset", header: "Year reset", render: (row) => (row.year_reset ? "Yes" : "No"), width: "100px" },
  { key: "counters", header: "Next number per year", render: (row) => counters(row) },
];

export function NumberSequenceListPage() {
  const sequences = useNumberSequences();
  const rows = sequences.data?.pages.flatMap((page) => page.items) ?? [];

  return (
    <div>
      <header className="mb-6">
        <p className="text-[12px] text-ink-muted">
          <Link to="/admin" className="hover:text-ink">
            Admin
          </Link>{" "}
          / <span className="text-ink">Number Sequences</span>
        </p>
        <h1 className="mt-1.5 text-[22px] font-[650] tracking-[-0.01em] text-ink">Number Sequences</h1>
        <p className="mt-1 text-[13px] text-ink-muted">
          Read-only: sequences are created by document posting and the industry template; counters are never
          edited so document numbering stays gapless. Each year keeps its own counter, so a
          backdated document numbers in its own year without disturbing the current one.
        </p>
      </header>
      <div>
        {sequences.isError ? (
          <p role="alert" className="rounded-control bg-danger-tint px-3 py-2 text-sm text-danger">
            {getErrorMessage(sequences.error, "Unable to load number sequences.")}
          </p>
        ) : (
          <DataGrid
            columns={COLUMNS}
            rows={rows}
            rowKey={(row) => row.id}
            loading={sequences.isPending}
            emptyMessage="No number sequences yet — they appear when the first numbered document posts."
            hasMore={sequences.hasNextPage}
            onLoadMore={() => void sequences.fetchNextPage()}
            loadingMore={sequences.isFetchingNextPage}
            label="Number sequences"
          />
        )}
      </div>
    </div>
  );
}
