/**
 * Mirrors backend `app/modules/hospitality/schemas.py` (STRUCTURE §4): menu availability (the
 * 86 board), the advisory at-risk list, the menu read the property's website also uses, and the
 * order ticket with its lines. Money and quantities are Decimal-as-string (D-015), snake_case
 * untranslated.
 *
 * `MenuAvailabilityBoard` is the one name that does NOT match its backend class
 * (`MenuAvailabilityPage`): the page component that renders it is called `MenuAvailabilityPage`
 * too, and one of the two had to give. The wire shape is identical.
 */

import type { Page } from "@/lib/apiClient";

export type AvailabilityState = "AVAILABLE" | "LIMITED" | "EIGHTY_SIXED";
/** Who last wrote the row: a human, or the countdown flipping itself at zero. */
export type AvailabilitySource = "MANUAL" | "AUTO";
export type OrderTicketStatus =
  | "OPEN"
  | "SENT_TO_KITCHEN"
  | "IN_PREP"
  | "READY"
  | "SERVED"
  | "SETTLED"
  /** Terminal, reachable only from OPEN (D-080) — a check opened by mistake. Deliberately NOT a
   * step in `TICKET_FLOW`: see `ticketFlow.ts`. */
  | "CANCELLED";

// --- Menu availability --------------------------------------------------------

/** One item's RESOLVED availability — expiry already applied server-side, so a lapsed 86 never
 * reaches the client. Items with no stored row are simply absent from the board. */
export interface MenuAvailability {
  item_id: string;
  state: AvailabilityState;
  remaining_qty: string | null;
  available_until: string | null;
  reason: string | null;
  source: AvailabilitySource | null;
}

export interface MenuAvailabilitySet {
  state: AvailabilityState;
  remaining_qty?: string | null;
  available_until?: string | null;
  reason?: string | null;
}

/** The board plus the ONE instant it describes: two pages are two snapshots, so a client that
 * stitched them would render a state the kitchen was never in. */
export interface MenuAvailabilityBoard extends Page<MenuAvailability> {
  as_of: string;
}

/** Advisory and staff-only: how many more portions the storeroom covers, and the ingredient that
 * runs out first. It over-reports on shared ingredients by design — a human reads it and 86s. */
export interface MenuItemAtRisk {
  item_id: string;
  max_producible: number;
  limiting_item_id: string;
}

/** A sellable dish with its resolved price. `price` is null when no active general price list
 * prices it today — the dish is still listed, and ordering it is refused loudly instead. */
export interface MenuItem {
  item_id: string;
  item_code: string;
  name: string;
  description: string | null;
  category_id: string;
  price: string | null;
  currency_code: string | null;
}

// --- Order tickets ------------------------------------------------------------

export interface OrderTicketLine {
  id: string;
  line_number: number;
  item_id: string;
  quantity: string;
  unit_price: string;
  line_amount: string;
  seat_number: number | null;
  notes: string | null;
}

/** `quantity` is in the item's base UoM — a kitchen sells the dish in the unit it is costed in,
 * so there is no `uom_id` to send. */
export interface OrderTicketLineCreate {
  item_id: string;
  quantity: string;
  unit_price: string;
  seat_number?: number | null;
  notes?: string | null;
}

// No service date (#207): the server stamps today and the API does not accept one.
export interface OrderTicketCreate {
  table_code?: string | null;
  guest_count?: number | null;
  notes?: string | null;
  lines?: OrderTicketLineCreate[];
}

export interface OrderTicketLinesAdd {
  lines: OrderTicketLineCreate[];
}

/** `total_amount` is the maintained Σ line_amount and is authoritative over any price the client
 * cached. It is PRE-TAX (hospitality.md §6 limit 3) — the UI says so rather than implying a
 * tender amount. `document_id` is the D-012 registry id for the document-flow chain. */
export interface OrderTicket {
  id: string;
  document_id: string;
  ticket_number: string;
  status: OrderTicketStatus;
  opened_date: string;
  table_code: string | null;
  guest_count: number | null;
  fired_at: string | null;
  settled_at: string | null;
  cancelled_at: string | null;
  cancel_reason: string | null;
  total_amount: string;
  notes: string | null;
}

// --- Menu structure (#212, D-081) ---------------------------------------------
// TWO axes, because a restaurant has two: sections are a TREE and a dish sits in exactly one of
// them (that is the running order of a printed menu, and order implies a single place); tags are
// FLAT and a dish carries any number (vegan, spicy, Italian), which is what answers "show me
// everything vegan" without duplicating the dish into a second branch.

export interface MenuSection {
  id: string;
  name: string;
  parent_id: string | null;
  sort_order: number;
  /** DIRECT dishes only, never cumulative — a course showing its children's dishes would read as
   * "12 starters" on a heading that holds none of them itself. */
  dish_count: number;
}

export interface MenuSectionCreate {
  name: string;
  parent_id?: string | null;
  sort_order?: number;
}

export interface MenuSectionUpdate {
  name?: string;
  /** Needs `reparent` beside it: an optional nullable field cannot say the difference between
   * "leave the parent alone" and "make this a root section". */
  parent_id?: string | null;
  reparent?: boolean;
  sort_order?: number;
}

export interface MenuPlacement {
  item_id: string;
  section_id: string | null;
  tags: string[];
}

export interface MenuPlacementSet {
  section_id: string | null;
  tags: string[];
}
