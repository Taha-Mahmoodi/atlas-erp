/**
 * The actions a check may take: the ONE next step in the sequence, plus — while it is still OPEN —
 * cancelling it outright.
 *
 * The lifecycle is strictly sequential, so there is never a choice to present — `nextTicketStatus`
 * decides, and the UI never offers what `TICKET_FLOW` would refuse. Cancelling is the single
 * exception and it is a BRANCH, not a step (D-080): it is offered only from OPEN, because past the
 * fire the ingredients have left the storeroom and a walk-out becomes a money correction rather
 * than a status. It asks for a reason before it fires, since the API requires one. Each action carries its own
 * permission: `ticket.settle` is distinct from `ticket.manage` because settlement is the money
 * moment, so a server can run the floor without closing out checks.
 *
 * Firing has its own endpoint rather than being one more advance because it carries effects — the
 * 86 check, the countdown burn, the depletion jobs — that a generic status change must not skip.
 */

import { useState } from "react";

import { getErrorMessage } from "@/lib/apiClient";
import { useMe } from "@/lib/session";
import {
  useAdvanceTicket,
  useCancelTicket,
  useFireTicket,
  useSettleTicket,
} from "@/modules/hospitality/hooks";
import {
  canCancelTicket,
  nextTicketStatus,
  type NextTicketStatus,
} from "@/modules/hospitality/components/ticketFlow";
import type { OrderTicket } from "@/modules/hospitality/types";

/** OPEN is absent on purpose: it is the first state, so nothing ever advances INTO it and a
 * "reopen" label here would name an action the lifecycle has no transition for. */
const ACTION_LABEL: Record<NextTicketStatus, string> = {
  SENT_TO_KITCHEN: "Fire to kitchen",
  IN_PREP: "Start prep",
  READY: "Mark ready",
  SERVED: "Mark served",
  SETTLED: "Settle check",
};

export function TicketStatusFlow({
  ticket,
  onError,
}: {
  ticket: OrderTicket;
  /** Surfaces the backend's 422/409 where the page shows its error banner; null clears it. */
  onError: (message: string | null) => void;
}) {
  const me = useMe();
  const permissions = me.data?.permissions ?? [];
  const canManage = permissions.includes("hospitality.ticket.manage");
  const canSettle = permissions.includes("hospitality.ticket.settle");

  const fire = useFireTicket();
  const advance = useAdvanceTicket();
  const settle = useSettleTicket();
  const cancel = useCancelTicket();
  const [asking, setAsking] = useState(false);
  const [reason, setReason] = useState("");

  const next = nextTicketStatus(ticket.status);
  const cancellable = canCancelTicket(ticket.status) && canManage;
  if (next === null && !cancellable) return null;

  const allowed = next !== null && (next === "SETTLED" ? canSettle : canManage);
  if (!allowed && !cancellable) return null;

  const busy = fire.isPending || advance.isPending || settle.isPending || cancel.isPending;

  // Takes the target rather than closing over `next`: the null case is handled by not rendering
  // the button at all, and threading it through keeps that provable rather than asserted.
  const run = async (target: NextTicketStatus) => {
    onError(null);
    try {
      if (target === "SENT_TO_KITCHEN") {
        await fire.mutateAsync(ticket.id);
      } else if (target === "SETTLED") {
        await settle.mutateAsync(ticket.id);
      } else {
        await advance.mutateAsync({ ticketId: ticket.id, status: target });
      }
    } catch (caught) {
      onError(getErrorMessage(caught, `Unable to ${ACTION_LABEL[target].toLowerCase()}.`));
    }
  };

  const runCancel = async () => {
    onError(null);
    try {
      await cancel.mutateAsync({ ticketId: ticket.id, reason: reason.trim() });
      setAsking(false);
      setReason("");
    } catch (caught) {
      onError(getErrorMessage(caught, "Unable to cancel this check."));
    }
  };

  return (
    <div className="flex flex-wrap items-center gap-2">
      {allowed && next !== null && (
        <button type="button" onClick={() => void run(next)} disabled={busy} className="btn-ink">
          {busy ? "Working…" : ACTION_LABEL[next]}
        </button>
      )}
      {cancellable && !asking && (
        <button type="button" onClick={() => setAsking(true)} disabled={busy} className="btn-chip">
          Cancel check
        </button>
      )}
      {cancellable && asking && (
        // The reason is required by the API, so it is asked for here rather than sent empty —
        // "why is this table's check gone" is the question cancelling exists to answer.
        <div className="flex flex-wrap items-center gap-2">
          <label htmlFor="cancel-reason" className="text-xs text-ink-muted">
            Reason
          </label>
          <input
            id="cancel-reason"
            autoFocus
            value={reason}
            maxLength={200}
            onChange={(event) => setReason(event.target.value)}
            placeholder="Opened on the wrong table"
            className="w-56 rounded-control border border-line bg-surface px-2 py-1.5 text-sm text-ink"
          />
          <button
            type="button"
            onClick={() => void runCancel()}
            disabled={busy || reason.trim() === ""}
            className="btn-ink"
          >
            {cancel.isPending ? "Cancelling…" : "Confirm cancel"}
          </button>
          <button
            type="button"
            onClick={() => {
              setAsking(false);
              setReason("");
            }}
            className="btn-chip"
          >
            Keep check
          </button>
        </div>
      )}
    </div>
  );
}
