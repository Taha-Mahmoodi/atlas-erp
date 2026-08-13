import { useInfiniteQuery, useMutation, useQueryClient } from "@tanstack/react-query";

import {
  type ActivityFilters,
  cancelActivity,
  completeActivity,
  createActivity,
  listActivities,
} from "@/modules/crm/api";
import type { ActivityCreate } from "@/modules/crm/types";

export function useActivities(filters: Omit<ActivityFilters, "cursor"> = {}) {
  return useInfiniteQuery({
    queryKey: ["crm", "activities", filters],
    queryFn: ({ pageParam }) =>
      listActivities({ ...filters, ...(pageParam ? { cursor: pageParam } : {}) }),
    initialPageParam: undefined as string | undefined,
    getNextPageParam: (lastPage) => lastPage.next_cursor ?? undefined,
  });
}

function invalidateActivities(queryClient: ReturnType<typeof useQueryClient>) {
  void queryClient.invalidateQueries({ queryKey: ["crm", "activities"] });
}

export function useCreateActivity() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (payload: ActivityCreate) => createActivity(payload),
    onSuccess: () => invalidateActivities(queryClient),
  });
}

/** id as a mutation argument — one hook instance serves a whole list/timeline. */
export function useCompleteActivity() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (activityId: string) => completeActivity(activityId),
    onSuccess: () => invalidateActivities(queryClient),
  });
}

export function useCancelActivity() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (activityId: string) => cancelActivity(activityId),
    onSuccess: () => invalidateActivities(queryClient),
  });
}
