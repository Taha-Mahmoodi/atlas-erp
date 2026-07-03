import { useInfiniteQuery, useMutation, useQuery, useQueryClient } from "@tanstack/react-query";

import {
  createJournalEntry,
  getJournalEntry,
  type JournalEntryFilters,
  listJournalEntries,
  postJournalEntry,
  reverseJournalEntry,
} from "@/modules/finance/api";
import type {
  JournalEntryCreate,
  JournalEntryReverseRequest,
} from "@/modules/finance/types";

/** Keyset-paginated (D-014) — pages accumulate via `fetchNextPage`, they don't replace. */
export function useJournalEntries(filters: Omit<JournalEntryFilters, "cursor"> = {}) {
  return useInfiniteQuery({
    queryKey: ["finance", "journal-entries", filters],
    queryFn: ({ pageParam }) =>
      listJournalEntries({ ...filters, ...(pageParam ? { cursor: pageParam } : {}) }),
    initialPageParam: undefined as string | undefined,
    getNextPageParam: (lastPage) => lastPage.next_cursor ?? undefined,
  });
}

export function useJournalEntry(entryId: string | undefined) {
  return useQuery({
    queryKey: ["finance", "journal-entry", entryId],
    queryFn: () => getJournalEntry(entryId as string),
    enabled: entryId !== undefined,
  });
}

export function useCreateJournalEntry() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (payload: JournalEntryCreate) => createJournalEntry(payload),
    onSuccess: () => {
      void queryClient.invalidateQueries({ queryKey: ["finance", "journal-entries"] });
    },
  });
}

export function usePostJournalEntry(entryId: string) {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: () => postJournalEntry(entryId),
    onSuccess: () => {
      void queryClient.invalidateQueries({ queryKey: ["finance", "journal-entries"] });
      void queryClient.invalidateQueries({ queryKey: ["finance", "journal-entry", entryId] });
    },
  });
}

export function useReverseJournalEntry(entryId: string) {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (payload: JournalEntryReverseRequest) => reverseJournalEntry(entryId, payload),
    onSuccess: () => {
      void queryClient.invalidateQueries({ queryKey: ["finance", "journal-entries"] });
      void queryClient.invalidateQueries({ queryKey: ["finance", "journal-entry", entryId] });
    },
  });
}
