/**
 * Mirrors backend `app/modules/quality/schemas.py` (STRUCTURE §4). PLAN 15.9: an inspection
 * lot is a header-only document — no create form (lots come from a flagged goods-receipt
 * line's posting, never the API), so there is no Create type; the client interacts through
 * the usage DECISION (accept/reject split with an optional disposition) and cancel.
 */

export type InspectionLotStatus = "OPEN" | "ACCEPTED" | "REJECTED" | "CANCELLED";

/** v1 creates lots from exactly one source. */
export type InspectionSource = "GOODS_RECEIPT";

// RETURN_TO_VENDOR is declared in the backend catalog but NOT implemented (422 if chosen),
// so the UI only ever offers SCRAP and BLOCK.
export type RejectDisposition = "SCRAP" | "BLOCK" | "RETURN_TO_VENDOR";

export interface InspectionLot {
  id: string;
  lot_number: string;
  status: InspectionLotStatus;
  source: InspectionSource;
  source_document_id: string;
  item_id: string;
  warehouse_id: string;
  bin_id: string;
  inspect_lot_id: string | null;
  serial_id: string | null;
  quantity: string;
  accepted_quantity: string;
  rejected_quantity: string;
  disposition: RejectDisposition | null;
  created_date: string;
  decided_date: string | null;
  decision_by: string | null;
  notes: string | null;
  created_at: string;
  updated_at: string;
}

/**
 * The usage decision: accepted + rejected MUST equal the lot quantity (one decision covers
 * the whole lot). rejected > 0 requires a disposition; BLOCK additionally requires the
 * destination quarantine bin.
 */
export interface InspectionDecidePayload {
  accepted_quantity: string;
  rejected_quantity: string;
  disposition?: RejectDisposition | null;
  blocked_bin_id?: string | null;
  notes?: string | null;
}
