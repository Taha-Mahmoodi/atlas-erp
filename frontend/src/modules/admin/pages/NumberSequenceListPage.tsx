/**
 * Per-tenant number sequences, read-only (STRUCTURE §4, D-012). The backend deliberately
 * ships no adjust endpoint — mutating next_value would break the gapless guarantee — so
 * this page is a pure viewer.
 */

import { Link } from "@tanstack/react-router";

import { getErrorMessage } from "@/lib/apiClient";
import { DataGrid, type DataGridColumn } from "@/components/DataGrid";
import { useNumberSequences } from "@/modules/admin/hooks";
import type { NumberSequence } from "@/modules/admin/types";

function preview(sequence: NumberSequence): string {
  return `${sequence.prefix}${String(sequence.next_value).padStart(sequence.padding, "0")}`;
}

const COLUMNS: DataGridColumn<NumberSequence>[] = [
  { key: "name", header: "Sequence", render: (row) => row.name },
  { key: "prefix", header: "Prefix", render: (row) => row.prefix, width: "140px" },
  { key: "next_value", header: "Next value", render: (row) => row.next_value, align: "right", width: "110px" },
  { key: "preview", header: "Next number", render: (row) => <span className="tabular-nums">{preview(row)}</span>, width: "160px" },
  { key: "year_reset", header: "Year reset", render: (row) => (row.year_reset ? "Yes" : "No"), width: "100px" },
  { key: "current_year", header: "Year", render: (row) => row.current_year ?? "—", align: "right", width: "80px" },
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
          edited so document numbering stays gapless.
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
