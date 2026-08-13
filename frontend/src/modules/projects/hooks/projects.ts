import { useInfiniteQuery, useMutation, useQuery, useQueryClient } from "@tanstack/react-query";

import {
  createProject,
  getProject,
  getProjectCostReport,
  listProjects,
  type ProjectFilters,
  updateProject,
} from "@/modules/projects/api";
import type { ProjectCreate, ProjectUpdate } from "@/modules/projects/types";

export function useProjects(filters: Omit<ProjectFilters, "cursor"> = {}) {
  return useInfiniteQuery({
    queryKey: ["projects", "projects", filters],
    queryFn: ({ pageParam }) => listProjects({ ...filters, ...(pageParam ? { cursor: pageParam } : {}) }),
    initialPageParam: undefined as string | undefined,
    getNextPageParam: (lastPage) => lastPage.next_cursor ?? undefined,
  });
}

export function useProject(projectId: string | undefined) {
  return useQuery({
    queryKey: ["projects", "project", projectId],
    queryFn: () => getProject(projectId as string),
    enabled: projectId !== undefined,
  });
}

function invalidateProjects(queryClient: ReturnType<typeof useQueryClient>, projectId?: string) {
  void queryClient.invalidateQueries({ queryKey: ["projects", "projects"] });
  if (projectId) void queryClient.invalidateQueries({ queryKey: ["projects", "project", projectId] });
}

export function useCreateProject() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (payload: ProjectCreate) => createProject(payload),
    onSuccess: () => invalidateProjects(queryClient),
  });
}

export function useUpdateProject(projectId: string) {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (payload: ProjectUpdate) => updateProject(projectId, payload),
    onSuccess: () => invalidateProjects(queryClient, projectId),
  });
}

/** The project cost report (D-056), cumulative through `asOf` when set. */
export function useProjectCostReport(projectId: string | undefined, asOf?: string) {
  return useQuery({
    queryKey: ["projects", "cost-report", projectId, asOf ?? null],
    queryFn: () => getProjectCostReport(projectId as string, asOf),
    enabled: projectId !== undefined,
  });
}
