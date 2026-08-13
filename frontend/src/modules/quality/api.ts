/**
 * Typed endpoint calls for the quality module (STRUCTURE §4): inspection lots only — list,
 * point read, the accept/reject usage decision, and cancel. No create endpoint exists (lots
 * come from the goods-receipt handler).
 */

import { api, newIdempotencyKey, type Page } from "@/lib/apiClient";
import type {
  InspectionDecidePayload,
  InspectionLot,
  InspectionLotStatus,
  InspectionSource,
} from "@/modules/quality/types";

export interface InspectionLotFilters {
  cursor?: string;
  limit?: number;
  status?: InspectionLotStatus;
  item_id?: string;
  source?: InspectionSource;
}

export function listInspectionLots(
  filters: InspectionLotFilters = {},
): Promise<Page<InspectionLot>> {
  return api.get<Page<InspectionLot>>("/quality/inspection-lots", { params: { ...filters } });
}

export function getInspectionLot(lotId: string): Promise<InspectionLot> {
  return api.get<InspectionLot>(`/quality/inspection-lots/${lotId}`);
}

export function decideInspectionLot(
  lotId: string,
  payload: InspectionDecidePayload,
): Promise<InspectionLot> {
  return api.post<InspectionLot>(`/quality/inspection-lots/${lotId}/decide`, payload, {
    idempotencyKey: newIdempotencyKey(),
  });
}

export function cancelInspectionLot(lotId: string): Promise<InspectionLot> {
  return api.post<InspectionLot>(`/quality/inspection-lots/${lotId}/cancel`, undefined);
}
