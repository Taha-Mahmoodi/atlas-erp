/**
 * All activities across the pipeline (STRUCTURE §4): status-filterable overview with
 * complete/cancel inline and a link to each activity's parent lead/opportunity. Creation
 * happens on the parent's workbench (the backend requires exactly one parent), never here.
 */

import { Link } from "@tanstack/react-router";
import { useState } from "react";

import { getErrorMessage } from "@/lib/apiClient";
import { formatDate } from "@/lib/format";
import { useMe } from "@/lib/session";
import { DataGrid, type DataGridColumn } from "@/components/DataGrid";
import { ActivityStatusChip } from "@/modules/crm/components/ActivityTimeline";
import { useActivities, useCancelActivity, useCompleteActivity } from "@/modules/crm/hooks";
import type { Activity, ActivityStatus } from "@/modules/crm/types";

function ParentLink({ activity }: { activity: Activity }) {
  if (activity.lead_id) {
    return (
      <Link to="/crm/leads/$leadId" params={{ leadId: activity.lead_id }} className="text-primary underline">
        Lead
      </Link>
    );
  }
  if (activity.opportunity_id) {
    return (
      <Link
        to="/crm/opportunities/$opportunityId"
        params={{ opportunityId: activity.opportunity_id }}
        className="text-primary underline"
      >
        Opportunity
      </Link>
    );
  }
  return <>—</>;
}

export function ActivityListPage() {
  const me = useMe();
  const canManage = (me.data?.permissions ?? []).includes("crm.activity.manage");
  const [status, setStatus] = useState<ActivityStatus | "">("");

  const activities = useActivities(status ? { status } : {});
  const complete = useCompleteActivity();
  const cancel = useCancelActivity();
  const [error, setError] = useState<string | null>(null);

  const rows = activities.data?.pages.flatMap((page) => page.items) ?? [];

  const act = async (mutation: typeof complete, activity: Activity, failure: string) => {
    setError(null);
    try {
      await mutation.mutateAsync(activity.id);
    } catch (caught) {
      setError(getErrorMessage(caught, failure));
    }
  };

  const columns: DataGridColumn<Activity>[] = [
    { key: "activity_type", header: "Type", render: (row) => row.activity_type, width: "90px" },
    { key: "subject", header: "Subject", render: (row) => row.subject },
    { key: "parent", header: "For", render: (row) => <ParentLink activity={row} />, width: "110px" },
    {
      key: "due_date",
      header: "Due",
      width: "120px",
      render: (row) => (row.due_date ? formatDate(row.due_date) : "—"),
    },
    {
      key: "completed_date",
      header: "Completed",
      width: "120px",
      render: (row) => (row.completed_date ? formatDate(row.completed_date) : "—"),
    },
    {
      key: "status",
      header: "Status",
      width: "120px",
      render: (row) => <ActivityStatusChip status={row.status} />,
    },
    ...(canManage
      ? [
          {
            key: "actions",
            header: "",
            width: "160px",
            align: "right" as const,
            render: (row: Activity) =>
              row.status === "OPEN" ? (
                <span className="flex justify-end gap-1">
                  <button
                    type="button"
                    onClick={() => void act(complete, row, "Unable to complete the activity.")}
                    disabled={complete.isPending}
                    className="rounded-control px-2 py-0.5 text-xs font-medium text-primary transition-colors duration-150 hover:bg-primary-tint disabled:opacity-45"
                  >
                    Complete
                  </button>
                  <button
                    type="button"
                    onClick={() => void act(cancel, row, "Unable to cancel the activity.")}
                    disabled={cancel.isPending}
                    className="rounded-control px-2 py-0.5 text-xs font-medium text-ink-muted transition-colors duration-150 hover:bg-panel hover:text-danger disabled:opacity-45"
                  >
                    Cancel
                  </button>
                </span>
              ) : null,
          },
        ]
      : []),
  ];

  return (
    <div>
      <h1 className="text-xl font-semibold text-ink">Activities</h1>

      {error && (
        <p role="alert" className="mt-4 rounded-control bg-danger-tint px-3 py-2 text-xs text-danger">
          {error}
        </p>
      )}

      <div className="mt-4">
        <select
          value={status}
          onChange={(event) => setStatus(event.target.value as ActivityStatus | "")}
          className="rounded-control border border-line bg-surface px-2 py-1.5 text-sm text-ink"
        >
          <option value="">All statuses</option>
          <option value="OPEN">Open</option>
          <option value="COMPLETED">Completed</option>
          <option value="CANCELLED">Cancelled</option>
        </select>
      </div>

      <div className="mt-4">
        <DataGrid
          columns={columns}
          rows={rows}
          rowKey={(row) => row.id}
          loading={activities.isPending}
          emptyMessage="No activities yet — log them from a lead or opportunity."
          hasMore={activities.hasNextPage}
          onLoadMore={() => void activities.fetchNextPage()}
          loadingMore={activities.isFetchingNextPage}
          label="Activities"
        />
      </div>
    </div>
  );
}
