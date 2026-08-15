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

/** Every state something can advance INTO — OPEN is excluded because it is where a check starts
 * and nothing moves back to it. Callers use it to key an exhaustive action table. */
export type NextTicketStatus = Exclude<OrderTicketStatus, "OPEN">;

/** The one state this ticket may move to, or null once it is settled (terminal). */
export function nextTicketStatus(status: OrderTicketStatus): NextTicketStatus | null {
  // The +1 can never land on TICKET_FLOW[0], so the result excludes OPEN by construction — a fact
  // the index expression cannot carry in its type, and one the tests pin.
  return (TICKET_FLOW[TICKET_FLOW.indexOf(status) + 1] as NextTicketStatus | undefined) ?? null;
}

export function isNextStatus(from: OrderTicketStatus, to: OrderTicketStatus): boolean {
  return nextTicketStatus(from) === to;
}
