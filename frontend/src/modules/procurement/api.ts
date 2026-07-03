/**
 * Typed endpoint calls for the procurement module (STRUCTURE §4): vendors + approved items,
 * approval rules. Requisitions, RFQs, POs, goods receipts, and invoice matches land in later
 * slices of PLAN 15.6.
 */

import { api, type Page } from "@/lib/apiClient";
import type {
  ApprovalRule,
  ApprovalRuleCreate,
  ApprovalRuleUpdate,
  ApprovalDocumentType,
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
