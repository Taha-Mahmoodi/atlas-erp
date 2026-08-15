# P1 — Hospitality Module UI Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use `superpowers:subagent-driven-development`
> (recommended) or `superpowers:executing-plans`. Steps use checkbox (`- [ ]`) syntax.

**Goal:** Staff can 86 a dish, run a countdown, work the ticket board, watch the kitchen display,
and read the at-risk list — the Phase 19 backend gets its human surface, in the porcelain design
system, following the anatomy the twelve existing module UIs share.

**Architecture:** A standard module UI: `modules/hospitality/{api.ts, types.ts, hooks/, pages/}`,
registered in the module registry and router, gated per-action on `hospitality.*` permissions. The
KDS is the shared `Kanban` in read-mostly mode over a status-filtered ticket query — the CRM
opportunity board's anatomy with statuses for stages. The one genuinely new thing in the codebase
is a polling interval on the KDS/board queries; everything else is assembly of shipped parts.

**Tech Stack:** React 18, TypeScript, TanStack Query + Router, the in-house component library
(`frontend/src/components/*`), vitest.

**Spec:** `remaining-work-plan.md` §P1; the shipped staff API
(`backend/app/modules/hospitality/router.py:68` — menu availability, at-risk, tickets with
`fire`/`advance`/`settle`); `docs/modules/hospitality.md` for semantics.

## Global Constraints

- **STRUCTURE §8.4**: 300-line TSX cap. The board pages are the risk — plan components out
  up front (`modules/hospitality/components/`), the #176 lesson.
- **CI's real gate is `tsc`**: the `StaticModuleRoute` union, the `ModuleLink` switch, the router
  tree and the `IconName` union all fail typecheck if half-wired — finish the registration task
  completely before pages.
- **Test convention**: pages ship without page tests (the repo has none); pure logic that wants a
  test is extracted to a `.ts` beside the page (the `wbsTree.test.ts` pattern). Component changes
  (StatusPill, Kanban) extend the component's existing `.test.tsx`.
- The backend is the guard; UI permission checks only hide affordances (`useMe()` +
  `permissions.includes(...)`, the `ItemListPage.tsx:32-33` idiom).

## The three findings that shape this plan

1. **The KDS is the CRM board with a different noun.** `OpportunityBoardPage.tsx:56-68` already
   demonstrates the whole shape: map a status enum to `KanbanColumn`s, render cards, call a
   mutation from `onItemMove`, surface the 422 via `getErrorMessage`. Ticket statuses are strictly
   sequential with no VOID (`constants.py:57-99`), and `advance` is the column move.
2. **Nothing in the frontend polls today** — zero `refetchInterval`/`setInterval`/`EventSource`
   hits outside the imperative `pollJob`. A kitchen display that never refreshes is furniture, so
   the KDS query is the codebase's first `refetchInterval`, added deliberately, with a comment
   saying it is the first and why (the global `staleTime: 30_000` in `queryClient.ts:16` would
   otherwise stall the board).
3. **Conditional GET stays server-only for now.** `apiClient` exposes no response headers, so the
   backend's ETag support on hospitality reads can't be used without extending the client. At
   staff-terminal request rates polling plain reads is fine; note it, don't build it.

## File Structure

```
frontend/src/modules/hospitality/
  api.ts             # typed endpoint fns; idempotency keys on ticket-creating POSTs
  types.ts           # DTO mirrors of backend/app/modules/hospitality/schemas.py, snake_case
  hooks/index.ts     # barrel
  hooks/menu.ts      # availability list/set/clear, at-risk
  hooks/tickets.ts   # ticket list/detail/lines + fire/advance/settle mutations + KDS query
  components/
    TicketStatusFlow.tsx   # the fire/advance/settle action row (shared by detail + board)
    AvailabilityEditor.tsx # the set-86/countdown form (FormBuilder fields + submit wiring)
  pages/
    HospitalityHomePage.tsx    # SECTIONS tile array, the InventoryHomePage shape
    MenuAvailabilityPage.tsx   # the 86 board: DataGrid + AvailabilityEditor
    AtRiskPage.tsx             # GET /menu/at-risk in a DataGrid
    TicketListPage.tsx         # DataGrid + filters + New ticket
    TicketFormPage.tsx         # open a ticket: table_code, guest_count, lines
    TicketDetailPage.tsx       # lines, totals, TicketStatusFlow actions
    KdsBoardPage.tsx           # Kanban over SENT_TO_KITCHEN / IN_PREP / READY
frontend/src/shell/moduleRegistry.ts   # + hospitality row
frontend/src/shell/ModuleLink.tsx      # + case
frontend/src/components/Icon/Icon.tsx  # + icon
frontend/src/components/StatusPill/StatusPill.tsx  # + hospitality status tones
frontend/src/router.tsx                # + route block + tree entries
```

---

## Task 1: Registration — make the module exist end to end

**Files:**
- Modify: `frontend/src/shell/moduleRegistry.ts:14-27` (union), `:41-63` (MODULES row:
  `key: "hospitality"`, `permissionPrefix: "hospitality."`, group `Operations`)
- Modify: `frontend/src/shell/ModuleLink.tsx:17-45` (add the case)
- Modify: `frontend/src/components/Icon/Icon.tsx:10-37` (+ `IconName`) and the sprite (one
  `<symbol>`)
- Modify: `frontend/src/router.tsx` (the home route only, this task)
- Create: `frontend/src/modules/hospitality/pages/HospitalityHomePage.tsx`

**Why first.** The registry/switch/union trio is type-checked; landing it with just the home page
gives a shippable increment (the module appears for permitted users, tiles link onward to routes
added per-task) and `moduleRegistry.ts:64-68` gating means users without `hospitality.*` never see
it — no flag needed.

- [ ] **Step 1:** HomePage in the `InventoryHomePage` SECTIONS shape: Menu & availability /
      Tickets / Kitchen display / At-risk.
- [ ] **Step 2:** Registry row + ModuleLink case + icon + home route + tree entry.
      Run: `cd frontend && npm run typecheck && npm run test && npm run build`.
- [ ] **Step 3: Commit.**

---

## Task 2: The API layer

**Files:**
- Create: `frontend/src/modules/hospitality/{api.ts, types.ts, hooks/index.ts, hooks/menu.ts,
  hooks/tickets.ts}`

**Interfaces (produced for every later task):**
- `types.ts` mirrors `backend/app/modules/hospitality/schemas.py` — read it and mirror
  faithfully (snake_case, enums as string unions matching `constants.py`).
- `api.ts` in the inventory shape (`modules/inventory/api.ts:89-91`): `listAvailability`,
  `setAvailability(itemId, payload)`, `clearAvailability(itemId)`, `listAtRisk`, `listTickets`,
  `getTicket`, `createTicket` (**with `idempotencyKey: newIdempotencyKey()`** — it creates a
  document), `addLines`, `fireTicket`, `advanceTicket`, `settleTicket`.
- Hooks in the masters.ts shape: list = `useInfiniteQuery` keyed
  `["hospitality", "<resource>", filters]`, detail = `useQuery`, mutations invalidate list + detail
  keys. Plus the board query:

```ts
// hooks/tickets.ts — the codebase's FIRST polling query; deliberate, see p1 plan finding 2.
// staleTime: 0 + refetchInterval beat the global 30s staleTime (lib/queryClient.ts:16),
// which would otherwise freeze a kitchen display between manual navigations.
export function useKdsTickets(statuses: OrderTicketStatus[]) {
  return useQuery({
    queryKey: ["hospitality", "kds", statuses],
    queryFn: () => listTickets({ status: statuses, limit: 200 }),
    staleTime: 0,
    refetchInterval: 10_000,
  });
}
```

  (Check first how `router.py`'s list endpoint takes status filters — single vs repeated param —
  and shape the call accordingly; do not guess.)

- [ ] **Step 1:** types + api + hooks. **Step 2:** typecheck. **Step 3: Commit.**

---

## Task 3: Menu availability and the at-risk list

**Files:**
- Create: `pages/MenuAvailabilityPage.tsx`, `pages/AtRiskPage.tsx`,
  `components/AvailabilityEditor.tsx`
- Modify: `frontend/src/components/StatusPill/StatusPill.tsx` (+ its `.test.tsx`)
- Modify: `frontend/src/router.tsx`

**Interfaces:**
- StatusPill gains tones for `AVAILABLE` (positive), `LIMITED` (warning), `EIGHTY_SIXED`
  (negative) **in the component's TONE_BY_STATUS map, not per-page** — extend
  `StatusPill.test.tsx` for the new words. While there, add the ticket words
  (`SENT_TO_KITCHEN`, `IN_PREP`, `READY`, `SERVED`; `OPEN`/`SETTLED` may exist — check).
- MenuAvailabilityPage: DataGrid of overrides (item, state pill, remaining count,
  `available_until`, source), a "Set availability" flow opening `AvailabilityEditor` — a
  FormBuilder with `state` select, `remaining_qty` number (required iff LIMITED — enforce in the
  submit handler, FormBuilder's required is decorative until #164 lands), `available_until` date,
  `reason` text. Clear-86 is a per-row action gated on `hospitality.menu.manage`.
- AtRiskPage: read-only DataGrid over `listAtRisk` — staff-facing only, exactly as Q2 scoped it.

- [ ] **Steps: build → typecheck/test → commit** (StatusPill change + its test in the same
      commit).

---

## Task 4: Tickets — list, open, detail

**Files:**
- Create: `pages/TicketListPage.tsx`, `pages/TicketFormPage.tsx`, `pages/TicketDetailPage.tsx`,
  `components/TicketStatusFlow.tsx`
- Modify: `frontend/src/router.tsx` (`$ticketId` param, camelCase per convention)

**Interfaces:**
- List: DataGrid (number, table_code, guests, status pill, total, opened), status filter
  `<select>`, "New ticket" gated `hospitality.ticket.manage`.
- Form: table_code, guest_count, notes; lines added on the detail page after create (the
  StockCount two-step shape) — keep the create payload minimal and follow what
  `POST /tickets` actually accepts (read `schemas.py`).
- Detail: lines table (seat, item, qty, note), totals (labelled **pre-tax** until Phase 20 Task 8
  lands — §6 limit 3 is honest in the UI, not hidden), and `TicketStatusFlow`: the next legal
  action only (fire when OPEN; advance through IN_PREP → READY → SERVED; settle when SERVED),
  each gated on its permission (`ticket.manage` vs `ticket.settle`), 422s surfaced via
  `getErrorMessage`. Sequential-only, no VOID — the UI never offers what `TICKET_FLOW` refuses.

- [ ] **Steps: build → typecheck/test → commit.**

---

## Task 5: The kitchen display

**Files:**
- Create: `pages/KdsBoardPage.tsx`
- Modify: `frontend/src/router.tsx`

**Interfaces:**
- `Kanban` (the CRM board anatomy, `OpportunityBoardPage.tsx:56-68`): columns SENT_TO_KITCHEN /
  IN_PREP / READY; card = ticket number, table_code, elapsed-since-fired, line summary.
  `onItemMove` calls `advanceTicket` and refuses non-adjacent moves client-side with the same
  message shape the backend would 422 (`hospitality.status_not_advanceable`).
- Data: `useKdsTickets` (Task 2), the polling query. Full-screen-friendly layout (a kitchen
  screen), `density` on the grid components where offered.
- If the ticket read exposes a prep-station field on lines, add a station `<select>` filter; if
  it does not, **skip it and say so in the PR** — do not invent a client-side grouping the data
  can't support (read `schemas.py`/`queries.py` first).

- [ ] **Steps: build → typecheck/test → commit.**

---

## Task 6: Docs

**Files:** `docs/modules/hospitality.md` (a short UI section: pages, permissions each needs),
`PROGRESS.md`, `README.md` (the Chapters rule does not apply here — follow this repo's
convention: README lists module UIs, add the row).

- [ ] Update, commit.

---

## Follow-on seams (planned, not built — added when their backends land)

- **Reservation book + seating UI** (after Phase 21): `pages/ReservationBookPage.tsx` — the day's
  book as a DataGrid ordered by slot, seat/no-show actions calling Phase 21's endpoints; a seat
  action pre-fills the TicketFormPage. Slot-capacity override editor for managers.
- **Rooms/folio UI** (after Phase 20): out of this plan's scope entirely; it is a second UI plan
  the size of this one (reservation calendar, folio detail with doc-flow viewer, night-audit
  trigger + business-date banner, housekeeping board on the same Kanban).

## Done when

- [ ] `npm run typecheck && npm run test && npm run build` green; CI frontend job green
- [ ] A user with only `hospitality.menu.read` sees the module, the menu pages, and no manage
      affordances; a user with none never sees the tile
- [ ] 86ing a dish, running a countdown, opening/firing/advancing/settling a ticket, and watching
      the board update within one poll interval all work against the live backend
- [ ] Every hospitality status renders a StatusPill tone (no default-gray leaks)
- [ ] No new page over 300 lines

## Self-review

Coverage against §P1's named gaps: menu management → Task 3, 86 toggle → Task 3, ticket board →
Tasks 4–5, KDS view → Task 5, at-risk list → Task 3. Names used across tasks match Task 2's
exports (`useKdsTickets`, `advanceTicket`, `setAvailability`). The two component-library edits
(StatusPill tones, first `refetchInterval`) are called out as deliberate, with tests where the
convention has them.
