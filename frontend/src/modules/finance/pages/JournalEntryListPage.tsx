/**
 * Journal entries list (STRUCTURE §4). Filterable by status, keyset-paginated (D-014); row
 * click opens the entry (its lines, and the post/reverse actions live on the detail page).
 */

import { Link, useNavigate } from "@tanstack/react-router";
import { useState } from "react";

import { formatDate } from "@/lib/format";
import { useMe } from "@/lib/session";
import { DataGrid, type DataGridColumn } from "@/components/DataGrid";
import { StatusPill } from "@/components/StatusPill";
import { useJournalEntries } from "@/modules/finance/hooks";
import type { EntryStatus, JournalEntry } from "@/modules/finance/types";

const COLUMNS: DataGridColumn<JournalEntry>[] = [
  { key: "entry_number", header: "Entry #", render: (row) => row.entry_number ?? "(draft)", width: "140px" },
  { key: "posting_date", header: "Posting date", render: (row) => formatDate(row.posting_date), width: "140px" },
  { key: "document_type", header: "Type", render: (row) => row.document_type, width: "110px" },
  { key: "description", header: "Description", render: (row) => row.description ?? "—" },
  { key: "status", header: "Status", render: (row) => <StatusPill status={row.status} />, width: "100px" },
];

export function JournalEntryListPage() {
  const navigate = useNavigate();
  const me = useMe();
  const canPost = (me.data?.permissions ?? []).includes("finance.journal.post");
  const [status, setStatus] = useState<EntryStatus | "">("");

  const entries = useJournalEntries(status ? { status } : {});
  const rows = entries.data?.pages.flatMap((page) => page.items) ?? [];

  return (
    <div>
      <div className="flex items-center justify-between">
        <h1 className="text-[22px] font-[650] tracking-[-0.01em] text-ink">Journal Entries</h1>
        {canPost && (
          <Link
            to="/finance/journal-entries/new"
            className="btn-ink"
          >
            New entry
          </Link>
        )}
      </div>

      <div className="mt-4">
        <select
          value={status}
          onChange={(event) => setStatus(event.target.value as EntryStatus | "")}
          className="rounded-control border border-line bg-surface px-2 py-1.5 text-sm text-ink"
        >
          <option value="">All statuses</option>
          <option value="DRAFT">Draft</option>
          <option value="POSTED">Posted</option>
          <option value="REVERSED">Reversed</option>
        </select>
      </div>

      <div className="mt-4">
        <DataGrid
          columns={COLUMNS}
          rows={rows}
          rowKey={(row) => row.id}
          onRowClick={(row) => void navigate({ to: "/finance/journal-entries/$entryId", params: { entryId: row.id } })}
          loading={entries.isPending}
          emptyMessage="No journal entries yet."
          hasMore={entries.hasNextPage}
          onLoadMore={() => void entries.fetchNextPage()}
          loadingMore={entries.isFetchingNextPage}
          label="Journal entries"
        />
      </div>
    </div>
  );
}
