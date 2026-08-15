import { useInfiniteQuery, useMutation, useQuery, useQueryClient } from "@tanstack/react-query";

import {
  addTicketLines,
  advanceTicket,
  createTicket,
  fireTicket,
  getTicket,
  listTicketLines,
  listTickets,
  settleTicket,
  type TicketFilters,
} from "@/modules/hospitality/api";
import type {
  OrderTicketCreate,
  OrderTicketLinesAdd,
  OrderTicketStatus,
} from "@/modules/hospitality/types";

export function useTickets(filters: Omit<TicketFilters, "cursor"> = {}) {
  return useInfiniteQuery({
    queryKey: ["hospitality", "tickets", filters],
    queryFn: ({ pageParam }) =>
      listTickets({ ...filters, ...(pageParam ? { cursor: pageParam } : {}) }),
    initialPageParam: undefined as string | undefined,
    getNextPageParam: (lastPage) => lastPage.next_cursor ?? undefined,
  });
}

export function useTicket(ticketId: string | undefined) {
  return useQuery({
    queryKey: ["hospitality", "ticket", ticketId],
    queryFn: () => getTicket(ticketId as string),
    enabled: ticketId !== undefined,
  });
}

export function useTicketLines(ticketId: string | undefined) {
  return useQuery({
    queryKey: ["hospitality", "ticket-lines", ticketId],
    queryFn: () => listTicketLines(ticketId as string),
    enabled: ticketId !== undefined,
  });
}

/**
 * One kitchen-display column. **The codebase's first polling query**, added deliberately: nothing
 * in the frontend polled before this (the imperative `pollJob` aside), and a kitchen display that
 * only refreshes when someone navigates is furniture. `staleTime: 0` is required as well as the
 * interval — the global 30s staleTime (lib/queryClient.ts) would otherwise serve the cache back
 * on every refetch and freeze the board between manual navigations.
 *
 * ONE status per query because `GET /tickets` takes `status` as a single value, and the board's
 * three columns are three statuses — so three queries, which TanStack runs in parallel and caches
 * per column. Widening the endpoint to a repeated param would be a backend change for something
 * the client already gets for free.
 */
export function useKdsColumn(status: OrderTicketStatus) {
  return useQuery({
    queryKey: ["hospitality", "kds", status],
    queryFn: () => listTickets({ status, limit: 200 }),
    staleTime: 0,
    refetchInterval: 10_000,
    // The card's "time since fired" is computed from `new Date()` at render, so it needs a render
    // to move. With TanStack's default tracked props, a poll that returns identical JSON hands
    // back the same `data` reference and notifies nobody — the clock would freeze exactly when
    // nothing is moving, which is when a check sitting 12 minutes on the pass IS the alarm.
    notifyOnChangeProps: "all",
  });
}

function invalidateTicket(queryClient: ReturnType<typeof useQueryClient>, ticketId?: string) {
  void queryClient.invalidateQueries({ queryKey: ["hospitality", "tickets"] });
  void queryClient.invalidateQueries({ queryKey: ["hospitality", "kds"] });
  if (ticketId) {
    void queryClient.invalidateQueries({ queryKey: ["hospitality", "ticket", ticketId] });
    void queryClient.invalidateQueries({ queryKey: ["hospitality", "ticket-lines", ticketId] });
  }
}

export function useCreateTicket() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (payload: OrderTicketCreate) => createTicket(payload),
    onSuccess: () => invalidateTicket(queryClient),
  });
}

export function useAddTicketLines(ticketId: string) {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (payload: OrderTicketLinesAdd) => addTicketLines(ticketId, payload),
    onSuccess: () => invalidateTicket(queryClient, ticketId),
  });
}

/** Firing also burns countdowns and submits the depletion jobs, so the 86 board can change. */
export function useFireTicket() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (ticketId: string) => fireTicket(ticketId),
    onSuccess: (_data, ticketId) => {
      invalidateTicket(queryClient, ticketId);
      void queryClient.invalidateQueries({ queryKey: ["hospitality", "availability"] });
    },
  });
}

/** The ticket id is a mutation argument, so ONE hook instance serves a whole kanban board — the
 * `useMoveOpportunityStage` shape. */
export function useAdvanceTicket() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: ({ ticketId, status }: { ticketId: string; status: OrderTicketStatus }) =>
      advanceTicket(ticketId, status),
    onSettled: (_data, _error, { ticketId }) => invalidateTicket(queryClient, ticketId),
  });
}

export function useSettleTicket() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (ticketId: string) => settleTicket(ticketId),
    onSuccess: (_data, ticketId) => invalidateTicket(queryClient, ticketId),
  });
}
