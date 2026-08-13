import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";

import {
  createWbsElement,
  getWbsElement,
  listWbsElements,
  updateWbsElement,
} from "@/modules/projects/api";
import type { WbsElementCreate, WbsElementUpdate } from "@/modules/projects/types";

/** A project's full WBS set for the tree view and parent pickers.
 * ponytail: single 200-cap fetch (the option-lookup precedent); paginate when a real
 * project's breakdown outgrows it. */
export function useWbsElements(projectId: string | undefined) {
  return useQuery({
    queryKey: ["projects", "wbs", projectId],
    queryFn: () => listWbsElements(projectId as string, { limit: 200 }),
    enabled: projectId !== undefined,
  });
}

export function useWbsElement(wbsElementId: string | undefined) {
  return useQuery({
    queryKey: ["projects", "wbs-element", wbsElementId],
    queryFn: () => getWbsElement(wbsElementId as string),
    enabled: wbsElementId !== undefined,
  });
}

export function useCreateWbsElement(projectId: string) {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (payload: WbsElementCreate) => createWbsElement(projectId, payload),
    onSuccess: () => void queryClient.invalidateQueries({ queryKey: ["projects", "wbs", projectId] }),
  });
}

export function useUpdateWbsElement(wbsElementId: string) {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (payload: WbsElementUpdate) => updateWbsElement(wbsElementId, payload),
    onSuccess: (element) => {
      void queryClient.invalidateQueries({ queryKey: ["projects", "wbs", element.project_id] });
      void queryClient.invalidateQueries({ queryKey: ["projects", "wbs-element", wbsElementId] });
    },
  });
}
