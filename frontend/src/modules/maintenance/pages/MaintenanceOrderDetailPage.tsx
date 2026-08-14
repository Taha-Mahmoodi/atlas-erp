/**
 * The maintenance-order workbench (STRUCTURE §4): header + lifecycle actions gated on
 * status. DRAFT → schedule (date) → SCHEDULED → start → IN_PROGRESS → complete (records
 * actual cost, record-only — no GL posting, D-051) → COMPLETED; complete is also allowed
 * straight from SCHEDULED; cancel from any non-terminal state. A SCHEDULED order can be
 * re-scheduled (date updates, status unchanged). Costs display in the tenant's functional
 * currency — the order carries bare decimal amounts (MoneyType, no per-order currency).
 */

import { Link, useParams } from "@tanstack/react-router";
import { useState } from "react";

import { getErrorMessage } from "@/lib/apiClient";
import { formatDate, formatMoney } from "@/lib/format";
import { useMe } from "@/lib/session";
import { useFunctionalCurrency } from "@/modules/finance/hooks";
import {
  useCancelMaintenanceOrder,
  useCompleteMaintenanceOrder,
  useEquipmentLookup,
  useMaintenanceOrder,
  useMaintenancePlanLookup,
  useScheduleMaintenanceOrder,
  useStartMaintenanceOrder,
} from "@/modules/maintenance/hooks";
import type { MaintenanceOrder } from "@/modules/maintenance/types";
import { StatusPill } from "@/components/StatusPill";

function SchedulePanel({ order }: { order: MaintenanceOrder }) {
  const scheduleOrder = useScheduleMaintenanceOrder(order.id);
  const [scheduledDate, setScheduledDate] = useState(order.scheduled_date);
  const [error, setError] = useState<string | null>(null);
  const isDraft = order.status === "DRAFT";

  const schedule = async () => {
    setError(null);
    try {
      await scheduleOrder.mutateAsync({ scheduled_date: scheduledDate });
    } catch (caught) {
      setError(getErrorMessage(caught, "Unable to schedule the order."));
    }
  };

  return (
    <div className="mt-6 rounded-card border border-line bg-surface px-[18px] py-4 shadow-card">
      <h2 className="mono-caps mb-3.5 text-ink-muted">{isDraft ? "Schedule" : "Re-schedule"}</h2>
      {error && (
        <p role="alert" className="mb-3.5 rounded-control bg-danger-tint px-3 py-2 text-xs text-danger">
          {error}
        </p>
      )}
      <div className="flex items-end gap-2">
        <div>
          <label htmlFor="scheduled-date" className="mb-1 block text-xs font-medium text-ink-muted">
            Scheduled date
          </label>
          <input
            id="scheduled-date"
            type="date"
            value={scheduledDate}
            onChange={(event) => setScheduledDate(event.target.value)}
            className="rounded-control border border-line bg-surface px-2 py-1.5 text-sm text-ink"
          />
        </div>
        <button
          type="button"
          onClick={() => void schedule()}
          disabled={!scheduledDate || scheduleOrder.isPending}
          className="btn-ink"
        >
          {scheduleOrder.isPending ? "Scheduling…" : isDraft ? "Schedule" : "Update date"}
        </button>
      </div>
    </div>
  );
}

/** MoneyType decimal strings arrive as "150.000000" — trim trailing zeros for the
 * number-input prefill (string ops only, no float math on money). */
function trimCostInput(cost: string | null): string {
  return (cost ?? "").replace(/(\.\d*?)0+$/, "$1").replace(/\.$/, "");
}

function CompletePanel({ order }: { order: MaintenanceOrder }) {
  const completeOrder = useCompleteMaintenanceOrder(order.id);
  const [actualCost, setActualCost] = useState(trimCostInput(order.estimated_cost));
  const [completedDate, setCompletedDate] = useState("");
  const [error, setError] = useState<string | null>(null);

  const complete = async () => {
    setError(null);
    try {
      await completeOrder.mutateAsync({
        actual_cost: actualCost ? actualCost : null,
        completed_date: completedDate ? completedDate : null,
      });
    } catch (caught) {
      setError(getErrorMessage(caught, "Unable to complete the order."));
    }
  };

  const control = "rounded-control border border-line bg-surface px-2 py-1.5 text-sm text-ink";

  return (
    <div className="mt-6 rounded-card border border-line bg-surface px-[18px] py-4 shadow-card">
      <h2 className="mono-caps text-ink-muted">Complete</h2>
      <p className="mt-1 text-[12px] text-ink-muted">
        Records the actual cost on the order (record-only — no journal is posted).
      </p>
      {error && (
        <p role="alert" className="mt-2 rounded-control bg-danger-tint px-3 py-2 text-xs text-danger">
          {error}
        </p>
      )}
      <div className="mt-3.5 flex items-end gap-2">
        <div>
          <label htmlFor="actual-cost" className="mb-1 block text-xs font-medium text-ink-muted">
            Actual cost (optional)
          </label>
          <input
            id="actual-cost"
            type="number"
            min="0"
            step="0.01"
            value={actualCost}
            onChange={(event) => setActualCost(event.target.value)}
            className={control}
          />
        </div>
        <div>
          <label htmlFor="completed-date" className="mb-1 block text-xs font-medium text-ink-muted">
            Completed date (defaults to today)
          </label>
          <input
            id="completed-date"
            type="date"
            value={completedDate}
            onChange={(event) => setCompletedDate(event.target.value)}
            className={control}
          />
        </div>
        <button
          type="button"
          onClick={() => void complete()}
          disabled={completeOrder.isPending}
          className="rounded-control bg-success px-3 py-1.5 text-sm font-medium text-surface transition-colors duration-150 hover:opacity-90 disabled:cursor-not-allowed disabled:opacity-45"
        >
          {completeOrder.isPending ? "Completing…" : "Complete order"}
        </button>
      </div>
    </div>
  );
}

export function MaintenanceOrderDetailPage() {
  const { orderId } = useParams({ strict: false });
  const me = useMe();
  const canManage = (me.data?.permissions ?? []).includes("maintenance.order.manage");
  const canComplete = (me.data?.permissions ?? []).includes("maintenance.order.complete");

  const order = useMaintenanceOrder(orderId);
  const equipment = useEquipmentLookup();
  const plans = useMaintenancePlanLookup();
  const currency = useFunctionalCurrency();
  const startOrder = useStartMaintenanceOrder(orderId ?? "");
  const cancelOrder = useCancelMaintenanceOrder(orderId ?? "");
  const [error, setError] = useState<string | null>(null);

  if (order.isPending || !order.data) {
    return <p className="text-[13px] text-ink-muted">Loading…</p>;
  }
  const data = order.data;
  const currencyCode = currency.data ?? "—";
  const isTerminal = data.status === "COMPLETED" || data.status === "CANCELLED";
  const canSchedule = data.status === "DRAFT" || data.status === "SCHEDULED";
  const completable = data.status === "SCHEDULED" || data.status === "IN_PROGRESS";

  const unit = equipment.data?.items.find((e) => e.id === data.equipment_id);
  const plan = data.maintenance_plan_id
    ? plans.data?.items.find((p) => p.id === data.maintenance_plan_id)
    : undefined;

  const start = async () => {
    setError(null);
    try {
      await startOrder.mutateAsync();
    } catch (caught) {
      setError(getErrorMessage(caught, "Unable to start the order."));
    }
  };

  const cancel = async () => {
    setError(null);
    try {
      await cancelOrder.mutateAsync();
    } catch (caught) {
      setError(getErrorMessage(caught, "Unable to cancel the order."));
    }
  };

  return (
    <div className="mx-auto max-w-4xl">
      <header className="mb-6">
        <p className="text-[12px] text-ink-muted">
          <Link to="/maintenance/orders">Maintenance orders</Link> /{" "}
          <span className="text-ink">{data.order_number}</span>
        </p>
        <div className="mt-1.5 flex items-start justify-between gap-4">
          <div className="flex items-center gap-3">
            <h1 className="text-[22px] font-[650] tracking-[-0.01em] text-ink">{data.order_number}</h1>
            <StatusPill status={data.status} />
          </div>
          <div className="flex items-center gap-2.5">
            {!isTerminal && canManage && (
              <button
                type="button"
                onClick={() => void cancel()}
                disabled={cancelOrder.isPending}
                className="btn-chip hover:border-danger hover:text-danger"
              >
                Cancel
              </button>
            )}
            {data.status === "SCHEDULED" && canManage && (
              <button
                type="button"
                onClick={() => void start()}
                disabled={startOrder.isPending}
                className="btn-ink"
              >
                {startOrder.isPending ? "Starting…" : "Start work"}
              </button>
            )}
          </div>
        </div>
      </header>

      {error && (
        <p role="alert" className="mb-4 rounded-control bg-danger-tint px-3 py-2 text-xs text-danger">
          {error}
        </p>
      )}

      <dl className="mt-6 grid grid-cols-2 gap-x-6 gap-y-4 rounded-card border border-line bg-surface px-[18px] py-4 shadow-card sm:grid-cols-4">
        <div>
          <dt className="mono-caps text-ink-muted">Type</dt>
          <dd className="mt-1.5 text-[13px] text-ink">{data.order_type}</dd>
        </div>
        <div>
          <dt className="mono-caps text-ink-muted">Equipment</dt>
          <dd className="mt-1.5 text-[13px] text-ink">
            {unit ? `${unit.code} — ${unit.name}` : data.equipment_id}
          </dd>
        </div>
        <div>
          <dt className="mono-caps text-ink-muted">Plan</dt>
          <dd className="mt-1.5 text-[13px] text-ink">
            {data.maintenance_plan_id ? (
              <Link
                to="/maintenance/plans/$planId"
                params={{ planId: data.maintenance_plan_id }}
                className="text-primary underline"
              >
                {plan ? `${plan.code} — ${plan.name}` : "View plan"}
              </Link>
            ) : (
              "—"
            )}
          </dd>
        </div>
        <div>
          <dt className="mono-caps text-ink-muted">Scheduled</dt>
          <dd className="mt-1.5 text-[13px] text-ink">{formatDate(data.scheduled_date)}</dd>
        </div>
        <div>
          <dt className="mono-caps text-ink-muted">Completed</dt>
          <dd className="mt-1.5 text-[13px] text-ink">
            {data.completed_date ? formatDate(data.completed_date) : "—"}
          </dd>
        </div>
        <div>
          <dt className="mono-caps text-ink-muted">Estimated cost</dt>
          <dd className="mt-1.5 text-[13px] tabular-nums text-ink">
            {data.estimated_cost ? formatMoney(data.estimated_cost, currencyCode) : "—"}
          </dd>
        </div>
        <div>
          <dt className="mono-caps text-ink-muted">Actual cost</dt>
          <dd className="mt-1.5 text-[13px] tabular-nums text-ink">
            {data.actual_cost ? formatMoney(data.actual_cost, currencyCode) : "—"}
          </dd>
        </div>
        <div className="col-span-2">
          <dt className="mono-caps text-ink-muted">Description</dt>
          <dd className="mt-1.5 text-[13px] text-ink">{data.description}</dd>
        </div>
        <div className="col-span-2 sm:col-span-4">
          <dt className="mono-caps text-ink-muted">Notes</dt>
          <dd className="mt-1.5 text-[13px] text-ink">{data.notes ?? "—"}</dd>
        </div>
      </dl>

      {canSchedule && canManage && <SchedulePanel order={data} />}
      {completable && canComplete && <CompletePanel order={data} />}
    </div>
  );
}
