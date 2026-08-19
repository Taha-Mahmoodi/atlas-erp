/**
 * The order-ticket lifecycle as the UI needs it: what may happen next, and whether a proposed
 * move is that one thing. Mirrors `hospitality/constants.py`'s `TICKET_FLOW`, where the ORDER of
 * declaration is the contract and a transition is legal only to the NEXT state.
 *
 * Strictly sequential, not merely forward-only, and the reason is stock rather than tidiness:
 * SENT_TO_KITCHEN is the single point at which a ticket's ingredients are committed, so any
 * shortcut past it would be revenue with no depletion at all. There is no VOID — a comp or a
 * walk-out is a money correction the folio owns.
 *
 * The backend refuses an illegal move with 409 `hospitality.ticket_transition_invalid`; this is
 * what lets the UI avoid OFFERING one, so the kanban board never renders a move it knows will 422.
 */

import type { OrderTicketStatus } from "@/modules/hospitality/types";

export const TICKET_FLOW: readonly OrderTicketStatus[] = [
  "OPEN",
  "SENT_TO_KITCHEN",
  "IN_PREP",
  "READY",
  "SERVED",
  "SETTLED",
];

/** CANCELLED is deliberately absent from TICKET_FLOW above: it is a terminal BRANCH off OPEN
 * (D-080), not a step in the sequence, and the backend checks its one transition separately. */
const CANCELLABLE_FROM: OrderTicketStatus = "OPEN";

/** Whether this check may be cancelled — nothing cooked, no money moved. */
export function canCancelTicket(status: OrderTicketStatus): boolean {
  return status === CANCELLABLE_FROM;
}

/** Every state something can advance INTO — OPEN is excluded because it is where a check starts
 * and nothing moves back to it. Callers use it to key an exhaustive action table. */
export type NextTicketStatus = Exclude<OrderTicketStatus, "OPEN" | "CANCELLED">;

/** The one state this ticket may move to, or null once it is settled (terminal). */
export function nextTicketStatus(status: OrderTicketStatus): NextTicketStatus | null {
  const index = TICKET_FLOW.indexOf(status);
  // A status that is not IN the sequence has no next state. Without this guard indexOf's -1 makes
  // the +1 land on TICKET_FLOW[0] and a CANCELLED check would be offered "Fire to kitchen".
  if (index === -1) return null;
  // The +1 can never land on TICKET_FLOW[0], so the result excludes OPEN by construction — a fact
  // the index expression cannot carry in its type, and one the tests pin.
  return (TICKET_FLOW[index + 1] as NextTicketStatus | undefined) ?? null;
}

export function isNextStatus(from: OrderTicketStatus, to: OrderTicketStatus): boolean {
  return nextTicketStatus(from) === to;
}
