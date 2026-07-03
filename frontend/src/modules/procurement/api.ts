/**
 * Typed endpoint calls for the procurement module (STRUCTURE §4): vendors + approved items,
 * approval rules, purchase requisitions. RFQs, POs, goods receipts, and invoice matches land
 * in later slices of PLAN 15.6.
 */

import { api, newIdempotencyKey, type Page } from "@/lib/apiClient";
import type {
  ApprovalDecisionPayload,
  ApprovalDocumentType,
  ApprovalRule,
  ApprovalRuleCreate,
  ApprovalRuleUpdate,
  Requisition,
  RequisitionCreate,
  RequisitionDetail,
  RequisitionStatus,
  RequisitionUpdate,
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
