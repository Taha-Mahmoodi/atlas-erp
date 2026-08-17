/**
 * Typed endpoint calls for the hospitality module (STRUCTURE §4): the 86 board, the advisory
 * at-risk list, the menu read, and order tickets with their fire/advance/settle actions.
 *
 * Two calls here hit routes the backend mounts on its WEBSITE router (`website_router.py`) rather
 * than its staff one — `GET /menu` and `GET /menu/availability`. That is not a mistake and needs
 * no backend change: both routers share the `/api/v1/hospitality` prefix and both routes are
 * guarded by `hospitality.menu.read`, which every staff member who can see the 86 board already
 * holds. The staff router has no availability LIST of its own, only the per-item PUT/DELETE.
 *
 * Idempotency keys (D-013) go on the two POSTs with effects a retry must not repeat: creating a
 * ticket burns a gapless TKT- number, and firing one submits the depletion jobs that create stock
 * documents. The rest are either replay-safe (PUT replaces the one stored answer) or already
 * refused by the strictly-sequential lifecycle (`settle` twice is a 409).
 */

import { api, newIdempotencyKey, type Page } from "@/lib/apiClient";
import type {
  MenuAvailability,
  MenuAvailabilityBoard,
  MenuAvailabilitySet,
  MenuItem,
  MenuItemAtRisk,
  OrderTicket,
  OrderTicketCreate,
  OrderTicketLine,
  OrderTicketLinesAdd,
  OrderTicketStatus,
} from "@/modules/hospitality/types";

// --- Menu -------------------------------------------------------------------

export interface MenuFilters {
  cursor?: string;
  limit?: number;
  category_id?: string;
}

export function listMenu(filters: MenuFilters = {}): Promise<Page<MenuItem>> {
  return api.get<Page<MenuItem>>("/hospitality/menu", { params: { ...filters } });
}

/** The 86 board. Takes NO `limit`: the page is always MAX_LIMIT because everything ABSENT from
 * the board is available, and a client-sized page would silently claim a truncated tail is fine. */
export function listAvailability(cursor?: string): Promise<MenuAvailabilityBoard> {
  return api.get<MenuAvailabilityBoard>("/hospitality/menu/availability", {
    params: { ...(cursor ? { cursor } : {}) },
  });
}

export function setAvailability(
  itemId: string,
  payload: MenuAvailabilitySet,
): Promise<MenuAvailability> {
  return api.put<MenuAvailability>(`/hospitality/menu/${itemId}/availability`, payload);
}

/** Puts the dish back on the menu by deleting its override — absence IS the canonical AVAILABLE. */
export function clearAvailability(itemId: string): Promise<void> {
  return api.delete<void>(`/hospitality/menu/${itemId}/availability`);
}

export interface AtRiskFilters {
  threshold?: number;
  limit?: number;
}

export function listAtRisk(filters: AtRiskFilters = {}): Promise<MenuItemAtRisk[]> {
  return api.get<MenuItemAtRisk[]>("/hospitality/menu/at-risk", { params: { ...filters } });
}

// --- Order tickets ----------------------------------------------------------

export interface TicketFilters {
  cursor?: string;
  limit?: number;
  status?: OrderTicketStatus;
  opened_on?: string;
}

export function listTickets(filters: TicketFilters = {}): Promise<Page<OrderTicket>> {
  return api.get<Page<OrderTicket>>("/hospitality/tickets", { params: { ...filters } });
}

export function getTicket(ticketId: string): Promise<OrderTicket> {
  return api.get<OrderTicket>(`/hospitality/tickets/${ticketId}`);
}

export function listTicketLines(ticketId: string): Promise<OrderTicketLine[]> {
  return api.get<OrderTicketLine[]>(`/hospitality/tickets/${ticketId}/lines`);
}

export function createTicket(payload: OrderTicketCreate): Promise<OrderTicket> {
  return api.post<OrderTicket>("/hospitality/tickets", payload, {
    idempotencyKey: newIdempotencyKey(),
  });
}

export function addTicketLines(
  ticketId: string,
  payload: OrderTicketLinesAdd,
): Promise<OrderTicket> {
  return api.post<OrderTicket>(`/hospitality/tickets/${ticketId}/lines`, payload);
}

export function fireTicket(ticketId: string): Promise<OrderTicket> {
  return api.post<OrderTicket>(`/hospitality/tickets/${ticketId}/fire`, undefined, {
    idempotencyKey: newIdempotencyKey(),
  });
}

export function advanceTicket(
  ticketId: string,
  status: OrderTicketStatus,
): Promise<OrderTicket> {
  return api.post<OrderTicket>(`/hospitality/tickets/${ticketId}/advance`, { status });
}

export function settleTicket(ticketId: string): Promise<OrderTicket> {
  return api.post<OrderTicket>(`/hospitality/tickets/${ticketId}/settle`);
}

/** Close an OPEN check that should never have been opened (D-080). No idempotency key: the
 * terminal state refuses a second attempt on its own, exactly as settle does. */
export function cancelTicket(ticketId: string, reason: string): Promise<OrderTicket> {
  return api.post<OrderTicket>(`/hospitality/tickets/${ticketId}/cancel`, { reason });
}
