/**
 * Typed endpoint calls for the procurement module (STRUCTURE §4): vendors + approved items,
 * approval rules, purchase requisitions, RFQs, purchase orders. Goods receipts and invoice
 * matches land in later slices of PLAN 15.6.
 */

import { api, newIdempotencyKey, type Page } from "@/lib/apiClient";
import type {
  ApprovalDecisionPayload,
  ApprovalDocumentType,
  ApprovalRule,
  ApprovalRuleCreate,
  ApprovalRuleUpdate,
  PurchaseOrder,
  PurchaseOrderCreate,
  PurchaseOrderDetail,
  PurchaseOrderFromRequisition,
  PurchaseOrderFromRfq,
  PurchaseOrderStatus,
  RecordQuotePayload,
  Requisition,
  RequisitionCreate,
  RequisitionDetail,
  RequisitionStatus,
  RequisitionUpdate,
  Rfq,
  RfqCreate,
  RfqDetail,
  RfqFromRequisition,
  RfqStatus,
  Vendor,
  VendorApprovedItem,
  VendorApprovedItemCreate,
  VendorCreate,
  VendorStatus,
  VendorUpdate,
} from "@/modules/procurement/types";

export interface VendorFilters {
  cursor?: string;
  limit?: number;
  status?: VendorStatus;
}

export function listVendors(filters: VendorFilters = {}): Promise<Page<Vendor>> {
  return api.get<Page<Vendor>>("/procurement/vendors", { params: { ...filters } });
}

export function getVendor(vendorId: string): Promise<Vendor> {
  return api.get<Vendor>(`/procurement/vendors/${vendorId}`);
}

export function createVendor(payload: VendorCreate): Promise<Vendor> {
  return api.post<Vendor>("/procurement/vendors", payload);
}

export function updateVendor(vendorId: string, payload: VendorUpdate): Promise<Vendor> {
  return api.patch<Vendor>(`/procurement/vendors/${vendorId}`, payload);
}

export function listVendorApprovedItems(vendorId: string): Promise<VendorApprovedItem[]> {
  return api.get<VendorApprovedItem[]>(`/procurement/vendors/${vendorId}/approved-items`);
}

export function createVendorApprovedItem(
  vendorId: string,
  payload: VendorApprovedItemCreate,
): Promise<VendorApprovedItem> {
  return api.post<VendorApprovedItem>(`/procurement/vendors/${vendorId}/approved-items`, payload);
}

export function deleteVendorApprovedItem(vendorId: string, itemId: string): Promise<void> {
  return api.delete<void>(`/procurement/vendors/${vendorId}/approved-items/${itemId}`);
}

// --- Approval rules ------------------------------------------------------------

export interface ApprovalRuleFilters {
  cursor?: string;
  limit?: number;
  document_type?: ApprovalDocumentType;
  is_active?: boolean;
}

export function listApprovalRules(filters: ApprovalRuleFilters = {}): Promise<Page<ApprovalRule>> {
  return api.get<Page<ApprovalRule>>("/procurement/approval-rules", { params: { ...filters } });
}

export function getApprovalRule(ruleId: string): Promise<ApprovalRule> {
  return api.get<ApprovalRule>(`/procurement/approval-rules/${ruleId}`);
}

export function createApprovalRule(payload: ApprovalRuleCreate): Promise<ApprovalRule> {
  return api.post<ApprovalRule>("/procurement/approval-rules", payload);
}

export function updateApprovalRule(ruleId: string, payload: ApprovalRuleUpdate): Promise<ApprovalRule> {
  return api.patch<ApprovalRule>(`/procurement/approval-rules/${ruleId}`, payload);
}

// --- Purchase requisitions -------------------------------------------------------

export interface RequisitionFilters {
  cursor?: string;
  limit?: number;
  status?: RequisitionStatus;
  requested_by?: string;
}

export function listRequisitions(filters: RequisitionFilters = {}): Promise<Page<Requisition>> {
  return api.get<Page<Requisition>>("/procurement/requisitions", { params: { ...filters } });
}

export function getRequisition(requisitionId: string): Promise<RequisitionDetail> {
  return api.get<RequisitionDetail>(`/procurement/requisitions/${requisitionId}`);
}

export function createRequisition(payload: RequisitionCreate): Promise<RequisitionDetail> {
  return api.post<RequisitionDetail>("/procurement/requisitions", payload, {
    idempotencyKey: newIdempotencyKey(),
  });
}

export function updateRequisition(
  requisitionId: string,
  payload: RequisitionUpdate,
): Promise<RequisitionDetail> {
  return api.patch<RequisitionDetail>(`/procurement/requisitions/${requisitionId}`, payload);
}

export function submitRequisition(requisitionId: string): Promise<RequisitionDetail> {
  return api.post<RequisitionDetail>(`/procurement/requisitions/${requisitionId}/submit`, undefined, {
    idempotencyKey: newIdempotencyKey(),
  });
}

export function decideRequisition(
  requisitionId: string,
  payload: ApprovalDecisionPayload,
): Promise<RequisitionDetail> {
  return api.post<RequisitionDetail>(`/procurement/requisitions/${requisitionId}/decision`, payload, {
    idempotencyKey: newIdempotencyKey(),
  });
}

export function cancelRequisition(requisitionId: string): Promise<RequisitionDetail> {
  return api.post<RequisitionDetail>(`/procurement/requisitions/${requisitionId}/cancel`, undefined);
}

export function convertRequisitionToRfq(
  requisitionId: string,
  payload: RfqFromRequisition,
): Promise<RfqDetail> {
  return api.post<RfqDetail>(`/procurement/requisitions/${requisitionId}/convert-to-rfq`, payload, {
    idempotencyKey: newIdempotencyKey(),
  });
}

export function convertRequisitionToPurchaseOrder(
  requisitionId: string,
  payload: PurchaseOrderFromRequisition,
): Promise<PurchaseOrderDetail> {
  return api.post<PurchaseOrderDetail>(
    `/procurement/requisitions/${requisitionId}/convert-to-po`,
    payload,
    { idempotencyKey: newIdempotencyKey() },
  );
}

// --- RFQs ------------------------------------------------------------------------

export interface RfqFilters {
  cursor?: string;
  limit?: number;
  status?: RfqStatus;
  vendor_id?: string;
}

export function listRfqs(filters: RfqFilters = {}): Promise<Page<Rfq>> {
  return api.get<Page<Rfq>>("/procurement/rfqs", { params: { ...filters } });
}

export function getRfq(rfqId: string): Promise<RfqDetail> {
  return api.get<RfqDetail>(`/procurement/rfqs/${rfqId}`);
}

export function createRfq(payload: RfqCreate): Promise<RfqDetail> {
  return api.post<RfqDetail>("/procurement/rfqs", payload, {
    idempotencyKey: newIdempotencyKey(),
  });
}

export function sendRfq(rfqId: string): Promise<RfqDetail> {
  return api.post<RfqDetail>(`/procurement/rfqs/${rfqId}/send`, undefined, {
    idempotencyKey: newIdempotencyKey(),
  });
}

export function recordRfqQuote(rfqId: string, payload: RecordQuotePayload): Promise<RfqDetail> {
  return api.post<RfqDetail>(`/procurement/rfqs/${rfqId}/record-quote`, payload, {
    idempotencyKey: newIdempotencyKey(),
  });
}

export function closeRfq(rfqId: string): Promise<RfqDetail> {
  return api.post<RfqDetail>(`/procurement/rfqs/${rfqId}/close`, undefined);
}

export function convertRfqToPurchaseOrder(
  rfqId: string,
  payload: PurchaseOrderFromRfq,
): Promise<PurchaseOrderDetail> {
  return api.post<PurchaseOrderDetail>(`/procurement/rfqs/${rfqId}/convert-to-po`, payload, {
    idempotencyKey: newIdempotencyKey(),
  });
}

// --- Purchase orders ---------------------------------------------------------------

export interface PurchaseOrderFilters {
  cursor?: string;
  limit?: number;
  status?: PurchaseOrderStatus;
  vendor_id?: string;
}

export function listPurchaseOrders(filters: PurchaseOrderFilters = {}): Promise<Page<PurchaseOrder>> {
  return api.get<Page<PurchaseOrder>>("/procurement/purchase-orders", { params: { ...filters } });
}

export function getPurchaseOrder(purchaseOrderId: string): Promise<PurchaseOrderDetail> {
  return api.get<PurchaseOrderDetail>(`/procurement/purchase-orders/${purchaseOrderId}`);
}

export function createPurchaseOrder(payload: PurchaseOrderCreate): Promise<PurchaseOrderDetail> {
  return api.post<PurchaseOrderDetail>("/procurement/purchase-orders", payload, {
    idempotencyKey: newIdempotencyKey(),
  });
}

export function sendPurchaseOrder(purchaseOrderId: string): Promise<PurchaseOrderDetail> {
  return api.post<PurchaseOrderDetail>(`/procurement/purchase-orders/${purchaseOrderId}/send`, undefined, {
    idempotencyKey: newIdempotencyKey(),
  });
}

export function decidePurchaseOrder(
  purchaseOrderId: string,
  payload: ApprovalDecisionPayload,
): Promise<PurchaseOrderDetail> {
  return api.post<PurchaseOrderDetail>(
    `/procurement/purchase-orders/${purchaseOrderId}/decision`,
    payload,
    { idempotencyKey: newIdempotencyKey() },
  );
}

export function cancelPurchaseOrder(purchaseOrderId: string): Promise<PurchaseOrderDetail> {
  return api.post<PurchaseOrderDetail>(`/procurement/purchase-orders/${purchaseOrderId}/cancel`, undefined);
}
