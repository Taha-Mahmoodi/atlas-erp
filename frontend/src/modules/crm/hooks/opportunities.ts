import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";

import {
  convertOpportunity,
  createOpportunity,
  getKanbanBoard,
  getOpportunity,
  moveOpportunityStage,
  updateOpportunity,
} from "@/modules/crm/api";
import type { OpportunityCreate, OpportunityStage, OpportunityUpdate } from "@/modules/crm/types";

/** The whole pipeline board in one bounded call (D-057). */
export function useKanbanBoard() {
  return useQuery({
    queryKey: ["crm", "kanban"],
    queryFn: () => getKanbanBoard(),
  });
}

export function useOpportunity(opportunityId: string | undefined) {
  return useQuery({
    queryKey: ["crm", "opportunity", opportunityId],
    queryFn: () => getOpportunity(opportunityId as string),
    enabled: opportunityId !== undefined,
  });
}

function invalidateOpportunity(
  queryClient: ReturnType<typeof useQueryClient>,
  opportunityId?: string,
) {
  void queryClient.invalidateQueries({ queryKey: ["crm", "kanban"] });
  if (opportunityId) {
    void queryClient.invalidateQueries({ queryKey: ["crm", "opportunity", opportunityId] });
  }
}

export function useCreateOpportunity() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (payload: OpportunityCreate) => createOpportunity(payload),
    onSuccess: () => invalidateOpportunity(queryClient),
  });
}

export function useUpdateOpportunity(opportunityId: string) {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (payload: OpportunityUpdate) => updateOpportunity(opportunityId, payload),
    onSuccess: () => invalidateOpportunity(queryClient, opportunityId),
  });
}

/** The kanban move — id is a mutation argument so ONE hook instance serves the whole board. */
export function useMoveOpportunityStage() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: ({ opportunityId, stage }: { opportunityId: string; stage: OpportunityStage }) =>
      moveOpportunityStage(opportunityId, stage),
    onSettled: (_data, _error, { opportunityId }) =>
      invalidateOpportunity(queryClient, opportunityId),
  });
}

export function useConvertOpportunity(opportunityId: string) {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: () => convertOpportunity(opportunityId),
    onSuccess: () => {
      invalidateOpportunity(queryClient, opportunityId);
      // The convert created a sales customer + quote.
      void queryClient.invalidateQueries({ queryKey: ["sales", "customers"] });
      void queryClient.invalidateQueries({ queryKey: ["sales", "quotes"] });
    },
  });
}
