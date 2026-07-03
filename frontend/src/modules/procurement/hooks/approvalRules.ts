import { useInfiniteQuery, useMutation, useQuery, useQueryClient } from "@tanstack/react-query";

import {
  type ApprovalRuleFilters,
  createApprovalRule,
  getApprovalRule,
  listApprovalRules,
  updateApprovalRule,
} from "@/modules/procurement/api";
import type { ApprovalRuleCreate, ApprovalRuleUpdate } from "@/modules/procurement/types";

export function useApprovalRules(filters: Omit<ApprovalRuleFilters, "cursor"> = {}) {
  return useInfiniteQuery({
    queryKey: ["procurement", "approval-rules", filters],
    queryFn: ({ pageParam }) =>
      listApprovalRules({ ...filters, ...(pageParam ? { cursor: pageParam } : {}) }),
    initialPageParam: undefined as string | undefined,
    getNextPageParam: (lastPage) => lastPage.next_cursor ?? undefined,
  });
}

export function useApprovalRule(ruleId: string | undefined) {
  return useQuery({
    queryKey: ["procurement", "approval-rule", ruleId],
    queryFn: () => getApprovalRule(ruleId as string),
    enabled: ruleId !== undefined,
  });
}

export function useCreateApprovalRule() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (payload: ApprovalRuleCreate) => createApprovalRule(payload),
    onSuccess: () => {
      void queryClient.invalidateQueries({ queryKey: ["procurement", "approval-rules"] });
    },
  });
}

export function useUpdateApprovalRule(ruleId: string) {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (payload: ApprovalRuleUpdate) => updateApprovalRule(ruleId, payload),
    onSuccess: () => {
      void queryClient.invalidateQueries({ queryKey: ["procurement", "approval-rules"] });
      void queryClient.invalidateQueries({ queryKey: ["procurement", "approval-rule", ruleId] });
    },
  });
}
