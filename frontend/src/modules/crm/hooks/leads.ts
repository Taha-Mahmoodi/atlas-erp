import { useInfiniteQuery, useMutation, useQuery, useQueryClient } from "@tanstack/react-query";

import {
  convertLead,
  createLead,
  disqualifyLead,
  getLead,
  type LeadFilters,
  listLeads,
  qualifyLead,
  updateLead,
} from "@/modules/crm/api";
import type { ConvertLead, LeadCreate, LeadUpdate } from "@/modules/crm/types";

export function useLeads(filters: Omit<LeadFilters, "cursor"> = {}) {
  return useInfiniteQuery({
    queryKey: ["crm", "leads", filters],
    queryFn: ({ pageParam }) => listLeads({ ...filters, ...(pageParam ? { cursor: pageParam } : {}) }),
    initialPageParam: undefined as string | undefined,
    getNextPageParam: (lastPage) => lastPage.next_cursor ?? undefined,
  });
}

export function useLead(leadId: string | undefined) {
  return useQuery({
    queryKey: ["crm", "lead", leadId],
    queryFn: () => getLead(leadId as string),
    enabled: leadId !== undefined,
  });
}

function invalidateLead(queryClient: ReturnType<typeof useQueryClient>, leadId?: string) {
  void queryClient.invalidateQueries({ queryKey: ["crm", "leads"] });
  if (leadId) void queryClient.invalidateQueries({ queryKey: ["crm", "lead", leadId] });
}

export function useCreateLead() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (payload: LeadCreate) => createLead(payload),
    onSuccess: () => invalidateLead(queryClient),
  });
}

export function useUpdateLead(leadId: string) {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (payload: LeadUpdate) => updateLead(leadId, payload),
    onSuccess: () => invalidateLead(queryClient, leadId),
  });
}

export function useQualifyLead(leadId: string) {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: () => qualifyLead(leadId),
    onSuccess: () => invalidateLead(queryClient, leadId),
  });
}

export function useDisqualifyLead(leadId: string) {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: () => disqualifyLead(leadId),
    onSuccess: () => invalidateLead(queryClient, leadId),
  });
}

export function useConvertLead(leadId: string) {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (payload: ConvertLead) => convertLead(leadId, payload),
    onSuccess: () => {
      invalidateLead(queryClient, leadId);
      void queryClient.invalidateQueries({ queryKey: ["crm", "kanban"] });
    },
  });
}
