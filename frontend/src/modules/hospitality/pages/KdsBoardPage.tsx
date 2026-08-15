/**
 * The kitchen display (STRUCTURE §4): the shared Kanban over three status-filtered ticket queries,
 * the CRM pipeline's anatomy with kitchen states for stages.
 *
 * **This is the one screen in Atlas that refreshes itself.** Three `useKdsColumn` queries poll on
 * a 10s interval (hooks/tickets.ts) — the codebase's first `refetchInterval`, added deliberately,
 * because a kitchen display that only updates when someone navigates is furniture. The three
 * columns are three independent queries and can therefore land a beat apart; at a 10s interval on
 * a screen a cook glances at, that is invisible, and the alternative is a backend change to make
 * `status` a repeated parameter.
 *
 * A card leaves the board when it is SERVED, which is done from the check itself — tapping a card
 * opens it. The move menu offers only the adjacent step, so the board never proposes a transition
 * `TICKET_FLOW` would refuse.
 */

import { Link } from "@tanstack/react-router";
import { useState } from "react";

import { getErrorMessage } from "@/lib/apiClient";
import { formatElapsed } from "@/lib/format";
import { useMe } from "@/lib/session";
import { Kanban, type KanbanColumn } from "@/components/Kanban";
import { humanizeStatus } from "@/components/StatusPill";
import { isNextStatus } from "@/modules/hospitality/components/ticketFlow";
import { useAdvanceTicket, useKdsColumn } from "@/modules/hospitality/hooks";
import type { OrderTicket, OrderTicketStatus } from "@/modules/hospitality/types";

/** The kitchen's own queue. OPEN is the floor's, SERVED and SETTLED have left the pass. */
const KDS_STATUSES = ["SENT_TO_KITCHEN", "IN_PREP", "READY"] as const;

function Card({ ticket }: { ticket: OrderTicket }) {
  return (
    <Link
      to="/hospitality/tickets/$ticketId"
      params={{ ticketId: ticket.id }}
      className="block pr-4"
    >
      <span className="block text-[11px] text-ink-muted">{ticket.ticket_number}</span>
      <span className="block font-medium text-ink">
        {ticket.table_code ? `Table ${ticket.table_code}` : "No table"}
      </span>
      <span className="mt-1 block text-xs text-ink-muted">
        {ticket.guest_count ? `${ticket.guest_count} covers · ` : ""}
        <span className="tabular-nums text-ink">
          {ticket.fired_at ? formatElapsed(ticket.fired_at) : "—"}
        </span>
      </span>
    </Link>
  );
}

export function KdsBoardPage() {
  const me = useMe();
  const canManage = (me.data?.permissions ?? []).includes("hospitality.ticket.manage");
  const advance = useAdvanceTicket();
  const [error, setError] = useState<string | null>(null);

  // One query per column: `GET /tickets` takes a single `status`, and TanStack runs the three in
  // parallel. Hooks are called unconditionally in a fixed order, so this is not a loop over data.
  const sentToKitchen = useKdsColumn("SENT_TO_KITCHEN");
  const inPrep = useKdsColumn("IN_PREP");
  const ready = useKdsColumn("READY");
  const byStatus = { SENT_TO_KITCHEN: sentToKitchen, IN_PREP: inPrep, READY: ready };

  const columns: KanbanColumn<OrderTicket>[] = KDS_STATUSES.map((status) => ({
    key: status,
    title: humanizeStatus(status),
    items: byStatus[status].data?.items ?? [],
  }));

  const onItemMove = (ticketId: string, fromColumn: string, toColumn: string) => {
    setError(null);
    // Refused client-side with the message the backend would 422 with, rather than sent and
    // bounced: the lifecycle is strictly sequential, and a cook dragging a check two columns
    // deserves to be told why instead of watching it snap back.
    if (!isNextStatus(fromColumn as OrderTicketStatus, toColumn as OrderTicketStatus)) {
      setError(
        `A check moves one step at a time: ${humanizeStatus(fromColumn)} cannot go straight to ${humanizeStatus(toColumn).toLowerCase()}.`,
      );
      return;
    }
    advance.mutate(
      { ticketId, status: toColumn as OrderTicketStatus },
      { onError: (caught) => setError(getErrorMessage(caught, "Unable to move the check.")) },
    );
  };

  const loading = sentToKitchen.isPending || inPrep.isPending || ready.isPending;
  // A 5xx or a dropped network gives up after two retries (lib/queryClient.ts) and leaves the last
  // snapshot on screen under a header promising a 10s refresh — a board that LOOKS live while
  // frozen is the one failure a kitchen display cannot have.
  const stalled = sentToKitchen.isError || inPrep.isError || ready.isError;

  return (
    <div>
      <header className="mb-6">
        <p className="text-[12px] text-ink-muted">
          <Link to="/hospitality" className="hover:underline">
            Hospitality
          </Link>{" "}
          / <span className="text-ink">Kitchen display</span>
        </p>
        <h1 className="mt-1.5 text-[22px] font-[650] tracking-[-0.01em] text-ink">
          Kitchen display
        </h1>
        <p className="mt-1 text-[12px] text-ink-muted">
          Refreshes every 10 seconds. Open a check to serve or settle it.
        </p>
      </header>

      {error && (
        <p role="alert" className="mt-4 rounded-control bg-danger-tint px-3 py-2 text-xs text-danger">
          {error}
        </p>
      )}

      {stalled && (
        <p role="alert" className="mt-4 rounded-control bg-danger-tint px-3 py-2 text-xs text-danger">
          The board stopped refreshing — what you see below may be out of date. Check the
          connection; it retries on its own.
        </p>
      )}

      <div className="mt-6">
        {loading ? (
          <p className="text-[13px] text-ink-muted">Loading…</p>
        ) : (
          <Kanban
            columns={columns}
            itemKey={(ticket) => ticket.id}
            renderItem={(ticket) => <Card ticket={ticket} />}
            {...(canManage ? { onItemMove } : {})}
            emptyHint="Nothing waiting"
          />
        )}
      </div>
    </div>
  );
}
