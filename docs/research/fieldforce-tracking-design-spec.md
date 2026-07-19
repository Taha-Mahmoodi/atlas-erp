# Field Force Tracking — Design Spec

Design spec for a new Atlas module tracking marketers/sales reps in real time from a tablet: location, activity, tasks, goals, and zones. Precursor to a PLAN.md phase and, once each task is implemented, DECISIONS.md entries. Grounded in the category research in [field-force-tracking-market-scan.md](field-force-tracking-market-scan.md).

**Not part of the S/4HANA parity benchmark.** No core SAP capability corresponds to real-time field-rep GPS tracking (SAP's nearest adjacent product, Field Service Management, is a separate cloud offering outside S/4HANA core and outside this repo's benchmark). It is also outside the CRM module's stated v1 scope (D-057 excludes campaigns/marketing automation). Building it is a deliberate scope expansion beyond the parity map, tracked here rather than in `s4hana-parity.md`.

**Sequencing.** Built as **Phase 18**, after the existing Phase 15–17 build finishes and v1.0.0 promotes. Does not block or reorder the current Phase 15 frontend work.

## 1. Two distribution channels, one codebase

This module ships two ways from the same code:

1. **As an Atlas module** — enabled for a tenant already running the full ERP, alongside finance/inventory/sales/etc.
2. **As a standalone sellable product** — a leaner tenant profile for a customer who wants field tracking (and the sales/CRM integration it depends on) without buying the rest of the ERP.

Atlas already has the mechanism for this: the industry-template module-toggle system (Phase 14.1) turns modules on/off per tenant. The standalone edition is a new template profile, not new toggle infrastructure. Because order capture (§5, Slice D) needs Sales, and Sales's quote→order flow needs Inventory (ATP check) and Finance (billing→revenue journal) to behave correctly end-to-end, the standalone edition's minimal module set is: **core, hr, crm, sales, inventory, finance, reporting, fieldforce** — everything the module's own feature set actually depends on, nothing artificially stripped, nothing artificially added (manufacturing/procurement/quality/maintenance/projects/admin-extras stay off). A leaner fieldforce-only profile (no CRM/Sales/Inventory/Finance) remains possible later as a *different* toggle profile without any re-architecture — this is a config choice, not a fork.

For **distribution packaging** (docker-compose, README, marketing framing, default toggle profile pre-selected) a new long-lived branch, `product/fieldforce-standalone`, carries only packaging/config diffs on top of `dev` and is periodically fast-forward-merged from `dev` — it never carries its own logic changes. This needs a small amendment to GITHUB-WORKFLOW.md §2 ("exactly two long-lived branches") to permit long-lived `product/*` packaging branches under the same CI-must-pass rule, alongside `main`/`dev`. That amendment, plus the STRUCTURE.md amendment in §2 below, are **the first task of Phase 18** — not made now, since neither file should change until the code/branch they describe actually exists (matching how D-015/D-016 amended STRUCTURE.md when `core/money.py`/`core/custom_fields.py` were actually added).

## 2. Repo placement

- **Backend module:** `backend/app/modules/fieldforce/` — standard anatomy (`models.py`/`schemas.py`/`service/`/`router.py`/`events.py`/`handlers.py`/`constants.py`). No `queries.py` of its own in v1 — nothing else reads from fieldforce synchronously yet.
- **Tablet client:** new top-level `tablet/` (Capacitor + React + TypeScript, Android target), sibling to `backend/` and `frontend/`. Requires a STRUCTURE.md §1 amendment adding it to the canonical tree (done as Phase 18's first task, per §1 above).
- **Manager web UI:** `frontend/src/modules/fieldforce/`, following the existing module convention (`pages/`, `components/`, `api.ts`, `types.ts`, `hooks.ts`). One new design-system component, `LiveMap` (`frontend/src/components/LiveMap/`), ERP-agnostic per STRUCTURE §4 (takes pins/zones/callbacks, no fieldforce-specific knowledge).
- **Naming:** module key `fieldforce`; DB table prefix `ff_`; permission keys `fieldforce.<entity>.<action>`; routes `/api/v1/fieldforce/<resource-kebab-plural>`; new GitHub label `module:fieldforce`.

## 3. Scope decisions

| Decision | Choice | Why |
|---|---|---|
| Rep identity | Existing HR `employees`, extended with a `FieldRepProfile` | Reuses HR's person model via a cross-module read (`hr/queries.py`) instead of duplicating identity, per STRUCTURE §5 |
| Live-update model | Periodic refresh: tablet posts a ping on a configurable interval (default 30s), dashboard polls on a matching interval | Fits Atlas's REST-only backend; no websocket/SSE infrastructure exists or is needed |
| Platform | Android only | Matches the customer's tablet fleet |
| Client stack | Capacitor + React + TypeScript | Reuses the team's existing web stack/skillset; gets native background-location, camera, and offline-storage plugins |
| CRM/Sales linking | Optional — a visit may reference an existing lead/opportunity/customer, but doesn't require one | Covers both canvassing new prospects and visiting known accounts |
| Offline | Full local queue (pings, check-ins, task updates, photos), sync on reconnect | Category baseline; reps will lose signal in the field |
| Scale | Design for 300+ reps per tenant, multiple tenants | Drives the location-ping partitioning/archival design in §5 |
| Zone structure | Flat zone↔rep assignment (many-to-many) **plus** an optional Region → Territory → Zone hierarchy for roll-up reporting | Both were requested; the hierarchy is optional parentage, not a forced nesting |
| Goal metrics | Activity counts (native), sales value (reads Sales), and custom/configurable KPIs, all three | Reuses Reporting's existing generic report-builder engine (Phase 13.2) for the custom case instead of a second query engine |
| Order capture | In scope for v1 | Rides Sales's existing quote→order flow (ATP/credit-limit checks apply), via an event rather than a direct cross-module write |

## 4. Data model, by build slice

**Slice A — core, zones, location**
- `ff_field_rep_profiles`: `employee_id` (opaque FK via `hr/queries.py`), `device_id`, `tracking_consent_at`, `is_active`.
- `ff_regions`, `ff_territories` (`region_id` nullable FK), `ff_zones` (`territory_id` nullable FK, polygon stored as a plain JSON point array — not PostGIS, since the backend must stay SQLite-compatible for tests/demo per CLAUDE.md's tech stack; geofence math is a pure-Python point-in-polygon check with a per-zone configurable tolerance buffer for GPS drift, default 50m).
- `ff_zone_rep_assignments` (zone↔rep, many-to-many).
- `ff_location_pings`: `rep_profile_id`, `tenant_id`, `lat`, `lng`, `recorded_at` (device time), `received_at` (server time), `accuracy_m`, `battery_pct`, `synced_from_offline`. Indexed `(tenant_id, rep_profile_id, recorded_at)` per PERFORMANCE §1.
- Daily background job (reusing the existing job-runner core, PERFORMANCE §3 pattern) downsamples pings older than 30 days into an `ff_location_ping_archive` table (coarser resolution) — keeps the hot table bounded at 300+-rep scale.
- `GET /api/v1/fieldforce/reps/live` returns the latest ping per active rep in one query (no N+1, PERFORMANCE §2 budget) — what the manager dashboard polls.
- A geofence violation, detected at ping-ingestion time, raises `FieldGeofenceViolationDetected` and surfaces as an in-app alert (no push notification in v1 — periodic refresh was the chosen model).

**Slice B — visits & tasks**
- `ff_visits`: `rep_profile_id`, `zone_id`, optional opaque `crm_lead_id`/`crm_opportunity_id`/`sales_customer_id`, `checked_in_at`/`_lat`/`_lng`, `checked_out_at`, `notes`, `status`. Check-in requires the current ping to fall inside the assigned zone (plus tolerance buffer).
- `ff_visit_photos` (`visit_id`, storage reference, caption, `taken_at`).
- `ff_tasks`: `rep_profile_id` (nullable — pool task), `zone_id` (nullable), `title`, `description`, `due_date`, `priority`, simple `recurrence` (NONE/DAILY/WEEKLY), `status`, `completed_at`.

**Slice C — goals/KPIs**
- `ff_goal_definitions`: `name`, `metric_type` (ACTIVITY_COUNT | SALES_VALUE | CUSTOM), `scope` (REP/ZONE/TERRITORY/TEAM), `period`, `target_value`, `metric_config` (JSON). ACTIVITY_COUNT reads `ff_visits`/`ff_tasks` natively; SALES_VALUE reads `sales/queries.py`; CUSTOM reuses the Reporting module's existing whitelist-driven query engine (Phase 13.2) rather than a new one.
- Progress is computed on read (a "target vs. achievement" report), not stored.

**Slice D — order capture**
- Reads item/pricing via `sales/queries.py` (extended if needed with a rep-facing price-list lookup).
- `ff_visit_order_lines` (`visit_id`, opaque `item_id`, `quantity`, `unit_price` captured at entry time).
- On submit, fieldforce publishes `FieldOrderCaptured`; a new `sales/handlers.py` subscriber creates the real Sales Quote through Sales's existing flow (so ATP/credit-limit checks apply exactly as they do today), writing the docflow link back — mirroring how CRM's opportunity→quote convert already works.

**Slice E — offline & scale hardening**
- Tablet-side local SQLite queue (Capacitor SQLite plugin) with a client-generated idempotency key on every write, extending Atlas's existing idempotency-key convention (previously financial/stock documents only) to every fieldforce write endpoint, so a retried sync can't double-create a visit or ping.
- perf-suite case: bulk ping ingestion at 300-rep scale, asserting the ingestion endpoint and the live-map query both stay within PERFORMANCE §5/§2 budgets regardless of rep count.

## 5. Permissions & privacy

New keys: `fieldforce.zone.manage`/`.read`, `fieldforce.rep.manage`, `fieldforce.location.read` (kept separate from visit/task permissions — raw location history is sensitive employee data, deserving its own tightly-scoped grant), `fieldforce.visit.manage`/`.read`, `fieldforce.task.manage`/`.read`, `fieldforce.goal.manage`/`.read`, `fieldforce.order.create`.

A rep's `tracking_consent_at` must be set before their pings are accepted at all (pings from a rep without consent are rejected at the service layer) — the same privacy-conscious posture HR already applies to compensation data via field-level masking.

## 6. Events

Publishes: `FieldGeofenceViolationDetected`, `FieldVisitCheckedIn`, `FieldVisitCompleted`, `FieldOrderCaptured`. Sales gains the one other module's `handlers.py` change (subscribing to `FieldOrderCaptured`). No inbound subscriptions needed in v1.

## 7. Testing & documentation

Tests mirror source (STRUCTURE §6): `tests/modules/fieldforce/...`, one file per service aggregate; geofencing gets its own pure-function unit test file. `docs/modules/fieldforce.md` is written as the module is built (not at the end), matching every other module. Each task's DECISIONS.md entry is written when that task is actually implemented and verified, per this repo's established practice — not speculatively now.

## 8. Open risks, deferred to later

- **Android background-location behavior** is the single highest-uncertainty piece of this build (OS battery-optimization killing background tracking, permission friction). Not prototyped yet — first tablet-client task in the implementation plan should validate this early, on a real device, before the rest of Slice A locks in its assumptions.
- **True push notifications** (geofence alerts to a manager's phone, not just the in-app dashboard) are out of v1 — Atlas has no push infrastructure today.
- **A leaner fieldforce-only standalone profile** (no CRM/Sales/Inventory/Finance) is possible later as a separate toggle profile without re-architecture, if a smaller/cheaper SKU is wanted.
