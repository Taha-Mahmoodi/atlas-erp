# Remaining work — priorities and plans

Written 2026-08-14 while Phase 19 was building, to answer "what still needs doing" across the whole
repo rather than one phase at a time. Ordered by consequence, not by size.

Everything here is either already tracked as a GitHub issue, already named in a shipped
`DECISIONS.md` entry, or a gap one of the hospitality research passes surfaced and recorded.
Nothing here is new scope invented in this document.

---

## P0 — Job-runner reliability

**Why this is first, and why it is first *now*.** Phase 19 deliberately moved ingredient depletion
off the settle transaction onto the job runner. That was the right call — synchronous depletion
raised `EventCycleError` at 51 ingredient lines and refused guests' payments on phantom stock-outs —
but it converts a loud, in-your-face failure into a quiet row in a table. The hospitality research
was explicit that this trade is only acceptable if it is bought back:

> "A loud failure becomes quiet. Today a bad depletion is a 422 with a guest standing there; after
> this it is a FAILED job row nobody sees. **This must be bought back with FAILED-job alerting or
> the change is strictly worse than today** — and it lands on a pre-existing core gap: **there is no
> stale-PENDING sweeper**, so a job whose PENDING row committed but whose runner died to a restart
> stays PENDING forever with no retry. Tolerable for a stock count; **not tolerable for something
> with a GL effect.**"

Depletion has a GL effect. Until this lands, a backend restart mid-service silently loses COGS
postings, and nothing in Atlas will ever tell anyone.

### P0.1 Stale-PENDING sweeper

`submit_job` inserts a PENDING row inside the caller's transaction and the runner picks it up
post-commit (`core/jobs.py:13-16, 157, 183, 215`). If the process dies between the commit and the
pickup — a deploy, a container restart, an OOM — the row is PENDING forever. There is no reaper.

Scope: a startup sweep plus a periodic one that finds PENDING rows older than a threshold and
re-dispatches them, and RUNNING rows orphaned by a restart. Must be idempotent — a job handler may
run twice, so re-dispatch has to be safe, which for depletion means the handler checks whether the
ticket already has its issue moves. That check is the real work.

### P0.2 FAILED-job visibility

FAILED jobs are recorded (`jobs.py:304-312`) and nothing surfaces them. Minimum: an admin endpoint
listing FAILED/stale jobs for the tenant, and a KPI tile so it appears on a dashboard someone
actually looks at. This is the "bought back" clause above; without it Phase 19's concession is not
paid for.

### P0.3 Idempotency-key retention

`core_idempotency_keys` stores full response bodies forever (`core/idempotency.py:99`). Phase 19
gives a website a write channel, so that table now grows with guest traffic. Needs a retention
window and a purge, on the same sweeper mechanism as P0.1.

---

## P1 — Hospitality has no user interface

Phases 18, 19 and 20 are backend-only. There is no `frontend/src/modules/hospitality/`, so nothing
a human can look at: no menu management, no 86 toggle, no ticket board, no KDS view, no at-risk
list. Staff currently cannot 86 a dish without an API client.

This is a real gap rather than polish — Q2's whole design assumes "a human 86s", and there is no
surface for the human to do it on. It also has an existing pattern to follow: twelve module UIs
already exist, and the porcelain design system (v1.1.0) is the register.

Scope: menu + availability management, the ticket board with its status lifecycle, the KDS view as
a status-filtered query, and the at-risk list. Follows the module-UI anatomy the other twelve use.

---

## P2 — Open issues (all minor, all tracked)

| # | Title | Note |
|---|---|---|
| #163 | Kanban move-menu and aria-labels leak column totals baked into `column.title` | Accessibility; the fix is separating the count from the title rather than string-parsing it back out |
| #164 | FormBuilder renders `noValidate` and enforces nothing — required flags are visual-only | Touches every form in the app; needs care, and a decision about native vs. controlled validation |
| #165 | New-tenant admin from onboarding cannot read the masters its own template instantiated | Core/RBAC; smallest surface, sharpest confusion for a new tenant |
| #166 | Report-builder grid/CSV headers show wire column names instead of catalog labels | Contained to reporting |
| #176 | Nine files exceed the STRUCTURE §8.4 size caps | Split-only refactors, no behaviour change |

---

## P3 — Phase 20: Rooms & Folio

Planned at task level in `PLAN.md` (20.1–20.6) and specified in the hospitality plan's Q3 and Q5.
Deliberately last, for one reason beyond size: **20.4 widens finance's `CustomerReceipt` clearing
engine for advance deposits**, which is a change to shipped, in-production financial code. Every
other phase so far has been additive.

That work should land in `dev` and be reviewed by a human before it is promoted to `main`, unlike
Phases 18 and 19 which are new modules and can promote on their own merit.

Open questions Q3/Q5 already answered, carried here so the plan does not re-litigate them:
overbooking uses counter tables plus `with_for_update` and a portable CHECK — **not** a
PostgreSQL-only exclusion constraint, because D-003 requires the suite to run on SQLite; the
business date is its own concept and does not reuse fiscal periods; night audit is an idempotent
job on the existing runner.

---

## Deliberately not on this list

- **OTA/channel-manager sync, dynamic room pricing, loyalty, delivery-platform injection, KDS
  hardware, multi-property reporting, any AI feature.** All on the hospitality spec's explicit
  out-of-scope list.
- **Modifier-level 86 and day-part menus.** Named in Phase 19's out-of-scope section; modifiers are
  not modelled in Atlas at all, so this is a feature, not a gap.
- **A second credential shape (OAuth2 client-credentials).** D-069 records the reasoning: add it the
  day Atlas has external developers to delegate to, not before.
