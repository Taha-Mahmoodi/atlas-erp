/**
 * The activity timeline for ONE lead or opportunity (module-specific composite, STRUCTURE §4):
 * the parent-scoped list + a quick-add row + complete/cancel actions. The backend enforces
 * exactly-one-parent, so creation always happens here in context — never from a bare form.
 */

import { useState } from "react";

import { getErrorMessage } from "@/lib/apiClient";
import { formatDate } from "@/lib/format";
import {
  useActivities,
  useCancelActivity,
  useCompleteActivity,
  useCreateActivity,
} from "@/modules/crm/hooks";
import type { Activity, ActivityType } from "@/modules/crm/types";
import { StatusPill } from "@/components/StatusPill";

const CONTROL =
  "rounded-control border border-line bg-surface px-2 py-1 text-sm text-ink transition-colors duration-150 hover:border-ink-faint";
const TYPES: ActivityType[] = ["CALL", "EMAIL", "MEETING", "TASK", "NOTE"];
export function ActivityTimeline({
  parent,
  canManage,
}: {
  parent: { lead_id: string } | { opportunity_id: string };
  canManage: boolean;
}) {
  const activities = useActivities(parent);
  const createActivity = useCreateActivity();
  const complete = useCompleteActivity();
  const cancel = useCancelActivity();

  const [activityType, setActivityType] = useState<ActivityType>("CALL");
  const [subject, setSubject] = useState("");
  const [dueDate, setDueDate] = useState("");
  const [error, setError] = useState<string | null>(null);

  const rows = activities.data?.pages.flatMap((page) => page.items) ?? [];

  const add = async () => {
    setError(null);
    try {
      await createActivity.mutateAsync({
        activity_type: activityType,
        subject,
        due_date: dueDate || null,
        ...parent,
      });
      setSubject("");
      setDueDate("");
    } catch (caught) {
      setError(getErrorMessage(caught, "Unable to add the activity."));
    }
  };

  const act = async (mutation: typeof complete, activity: Activity, failure: string) => {
    setError(null);
    try {
      await mutation.mutateAsync(activity.id);
    } catch (caught) {
      setError(getErrorMessage(caught, failure));
    }
  };

  return (
    <section aria-label="Activities">
      <h2 className="text-sm font-semibold text-ink">Activities</h2>
      {error && (
        <p role="alert" className="mt-3 rounded-control bg-danger-tint px-3 py-2 text-xs text-danger">
          {error}
        </p>
      )}

      {canManage && (
        <div className="mt-3 flex flex-wrap items-end gap-2">
          <div>
            <label htmlFor="activity-type" className="mb-1 block text-xs font-medium text-ink-muted">
              Type
            </label>
            <select
              id="activity-type"
              value={activityType}
              onChange={(event) => setActivityType(event.target.value as ActivityType)}
              className={CONTROL}
            >
              {TYPES.map((type) => (
                <option key={type} value={type}>
                  {type}
                </option>
              ))}
            </select>
          </div>
          <div className="min-w-48 flex-1">
            <label htmlFor="activity-subject" className="mb-1 block text-xs font-medium text-ink-muted">
              Subject
            </label>
            <input
              id="activity-subject"
              type="text"
              value={subject}
              onChange={(event) => setSubject(event.target.value)}
              placeholder="Intro call, follow-up email…"
              className={`${CONTROL} w-full placeholder:text-ink-faint`}
            />
          </div>
          <div>
            <label htmlFor="activity-due" className="mb-1 block text-xs font-medium text-ink-muted">
              Due
            </label>
            <input
              id="activity-due"
              type="date"
              value={dueDate}
              onChange={(event) => setDueDate(event.target.value)}
              className={CONTROL}
            />
          </div>
          <button
            type="button"
            onClick={() => void add()}
            disabled={!subject.trim() || createActivity.isPending}
            className="btn-ink"
          >
            {createActivity.isPending ? "Adding…" : "Add"}
          </button>
        </div>
      )}

      <ul className="mt-3 divide-y divide-line rounded-card border border-line bg-surface shadow-card">
        {!activities.isPending && rows.length === 0 && (
          <li className="px-4 py-6 text-center text-sm text-ink-muted">No activities logged yet.</li>
        )}
        {rows.map((activity) => (
          <li key={activity.id} className="flex items-center gap-3 px-4 py-2.5 text-sm">
            <span className="w-16 shrink-0 text-[11px] font-semibold uppercase tracking-[0.02em] text-ink-muted">
              {activity.activity_type}
            </span>
            <span className="flex-1 text-ink">{activity.subject}</span>
            <span className="text-xs text-ink-muted">
              {activity.status === "COMPLETED" && activity.completed_date
                ? `Done ${formatDate(activity.completed_date)}`
                : activity.due_date
                  ? `Due ${formatDate(activity.due_date)}`
                  : "—"}
            </span>
            <StatusPill status={activity.status} />
            {canManage && activity.status === "OPEN" && (
              <span className="flex gap-1">
                <button
                  type="button"
                  onClick={() => void act(complete, activity, "Unable to complete the activity.")}
                  disabled={complete.isPending}
                  className="rounded-control px-2 py-0.5 text-xs font-medium text-primary transition-colors duration-150 hover:bg-primary-tint disabled:opacity-45"
                >
                  Complete
                </button>
                <button
                  type="button"
                  onClick={() => void act(cancel, activity, "Unable to cancel the activity.")}
                  disabled={cancel.isPending}
                  className="rounded-control px-2 py-0.5 text-xs font-medium text-ink-muted transition-colors duration-150 hover:bg-panel hover:text-danger disabled:opacity-45"
                >
                  Cancel
                </button>
              </span>
            )}
          </li>
        ))}
      </ul>
      {activities.hasNextPage && (
        <button
          type="button"
          onClick={() => void activities.fetchNextPage()}
          disabled={activities.isFetchingNextPage}
          className="mt-2 rounded-control px-2 py-1 text-sm font-medium text-primary transition-colors duration-150 hover:bg-primary-tint disabled:opacity-45"
        >
          {activities.isFetchingNextPage ? "Loading…" : "Load more"}
        </button>
      )}
    </section>
  );
}
