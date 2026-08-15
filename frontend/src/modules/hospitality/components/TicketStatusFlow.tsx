/**
 * The one action a check may take next, and nothing else (the fire / advance / settle row).
 *
 * The lifecycle is strictly sequential, so there is never a choice to present — `nextTicketStatus`
 * decides, and the UI never offers what `TICKET_FLOW` would refuse. Each action carries its own
 * permission: `ticket.settle` is distinct from `ticket.manage` because settlement is the money
 * moment, so a server can run the floor without closing out checks.
 *
 * Firing has its own endpoint rather than being one more advance because it carries effects — the
 * 86 check, the countdown burn, the depletion jobs — that a generic status change must not skip.
 */

import { getErrorMessage } from "@/lib/apiClient";
import { useMe } from "@/lib/session";
import {
  useAdvanceTicket,
  useFireTicket,
  useSettleTicket,
} from "@/modules/hospitality/hooks";
import {
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

  const next = nextTicketStatus(ticket.status);
  if (next === null) return null;

  const allowed = next === "SETTLED" ? canSettle : canManage;
  if (!allowed) return null;

  const busy = fire.isPending || advance.isPending || settle.isPending;

  const run = async () => {
    onError(null);
    try {
      if (next === "SENT_TO_KITCHEN") {
        await fire.mutateAsync(ticket.id);
      } else if (next === "SETTLED") {
        await settle.mutateAsync(ticket.id);
      } else {
        await advance.mutateAsync({ ticketId: ticket.id, status: next });
      }
    } catch (caught) {
      onError(getErrorMessage(caught, `Unable to ${ACTION_LABEL[next].toLowerCase()}.`));
    }
  };

  return (
    <button type="button" onClick={() => void run()} disabled={busy} className="btn-ink">
      {busy ? "Working…" : ACTION_LABEL[next]}
    </button>
  );
}
