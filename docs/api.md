# API Reference

The API reference is the OpenAPI spec the backend generates from its Pydantic schemas — it is never written by hand and never drifts from the code.

- **Interactive docs (Swagger UI):** `http://localhost:8000/api/v1/docs`
- **Raw spec:** `http://localhost:8000/api/v1/openapi.json`

Run the stack per the README quickstart (`docker-compose up`), then open either URL. Every endpoint lives under the versioned prefix `/api/v1`.

Conventions that apply across all endpoints — cursor pagination, the error envelope with machine codes, `Idempotency-Key` on financial/stock document creation, tenancy and auth headers — are specified in [architecture.md](architecture.md). Per-module behavior is documented in [`docs/modules/`](modules/).

## Machine API keys

A machine client — typically a property's own website calling Atlas as its backend — authenticates with a scoped API key instead of logging in. A key produces exactly the same principal a user's JWT does, so every endpoint, permission check, tenancy rule and idempotency rule behaves identically (**D-069**).

### 1. Issue a key

`POST /api/v1/admin/api-keys`, guarded by `admin.apikey.manage`:

```json
{
  "name": "property website",
  "user_id": "8f4e…",
  "scopes": ["sales.order.create", "sales.order.read"],
  "expires_at": null
}
```

- **`user_id`** must be a user in your own tenant (otherwise `404 admin.user_not_found`). The key is bound to that user and can never do more than the user can. **Bind it to a dedicated service user** (`website@yourproperty.example`, no password anyone uses, only the roles the site needs) — see the audit note below.
- **`scopes`** is optional. Omit it or send `null` and the key inherits its user's permissions unnarrowed. Send a list and the key's effective permissions are that list **intersected** with the user's — a scope the user does not hold grants nothing, and revoking the user's role narrows the key with it. Every entry is checked against the permission catalog; an unknown one is `422 rbac.unknown_permission`. The grantable universe is `GET /api/v1/admin/permissions`.
- **`expires_at`** is optional; after it passes, the key behaves exactly as if revoked.
- **Calling this endpoint *with a key* is restricted (D-070).** A key may never issue a key wider than itself: `scopes` becomes required and every entry must be one the calling key already holds. Sending `null` from a key is `403 rbac.scope_escalation` (whose `details.permitted_scopes` lists what you *could* have asked for), because "inherit the bound user" is not bounded by the caller. Logged in as a human, nothing changes — mint whatever the `admin.apikey.manage` permission allows.

### 2. The secret is shown once

The `201` body is the key's record plus one extra field, `key`, holding the full string — `atk_<your tenant id, hex, no dashes>_<secret>`. **This is the only time it exists anywhere.** Only its SHA-256 is stored, so a lost key is re-issued, never recovered.

Everything else stays readable from `GET /api/v1/admin/api-keys` (newest first, cursor-paginated, revoked and expired keys included). It never returns the secret or its digest, and `prefix` is only the non-secret half — `atk_<your tenant id>`, identical for every key you own. Tell keys apart by `name`, which is why it is required.

### 3. Send it

As an ordinary bearer token:

```
Authorization: Bearer atk_9f1c4b7e2d8a4f0b9c3e5a7d1f2b6c40_kJ2f…
```

Nothing else changes: no extra tenant header (the tenant rides in the key itself), no token refresh, no cookie, no CORS change. A malformed, unknown, revoked, expired or wrong-tenant key is a flat `401 auth.invalid_token` — the API never distinguishes between them.

### 4. Rotate with overlap

1. `POST /api/v1/admin/api-keys` to mint the replacement.
2. Deploy it to the client.
3. `POST /api/v1/admin/api-keys/{key_id}/revoke` on the old one.

Revocation takes effect on the credential's very next request — nothing caches the key — and is idempotent: revoking twice returns `200` with the first timestamp, so a retry is not an error. During the overlap the two keys are separate credentials with separate rate-limit budgets, so throughput is not halved.

### 5. What the audit trail shows

A key resolves to exactly the same principal its bound user's login does, so a write it makes is recorded like any other: `core_audit_log` gets a row whose `actor_user_id` is that user, and every document field that records who acted (`submitted_by`, `approver_id`, `approved_by`, `decision_by`) carries the same id. Nothing is unattributed, and nothing dangles — a key cannot be bound to a user outside its own tenant, and one bound to a deactivated user stops authenticating.

**There is no separate "this came from a machine" marker.** The audit row for a write your website made is indistinguishable from one the bound user made by hand. That is why the key belongs to a dedicated service user: the actor column then names the website, and an operator reading the trail can tell the two apart. Bind a key to a real person's account and the trail will attribute your website's writes to that person.

Issuing and revoking a key are themselves audited (`entity_table = core_api_keys`), so `GET /api/v1/admin/audit-logs` answers "who issued this credential, and when was it cut". The stored digest is never written to a diff.

### 6. Rate limiting (`429`)

`/api/` is limited to **10 requests/second with a burst of 20**, keyed on the `Authorization` header — so every key has its own budget and one client cannot throttle another. Excess requests are **rejected immediately** with `429`, not queued, so the right client behaviour is retry with backoff rather than waiting on a slow response. In practice a burst of ~22 gets through before the limiter engages, and the allowance refills at 10/s.

## The property website contract

A restaurant's own website is the first client Atlas ships a purpose-built surface for. It holds a
machine API key (above) scoped to `hospitality.menu.read` and `hospitality.ticket.manage` — nothing
else — and talks to three endpoints.

**Atlas ships a working one** (D-082): `frontend/src/modules/hospitality/website/`, served on its own
origin by its own nginx (`docker compose up` → <http://localhost:8080>), which is what holds the two
keys — the browser bundle never sees them and calls a relative `/guest-api/*` that carries no
credential at all. Read `frontend/website-nginx.conf.template` for the shape: one **exact** location
per contract endpoint (a `/menu/` prefix would also publish `/menu/at-risk`, the staff coverage scan),
`limit_except` per method, and a rate-limit zone keyed by address rather than by credential, because
every request through such a server presents the same key. If the site also takes **table bookings**, mint it a
**separate** key scoped to `hospitality.reservation.book` (see [the reservation
contract](#the-reservation-contract)) rather than widening this one: the two surfaces fail
differently, and a key that can only book cannot also read the menu it has no business changing.
Module behaviour is in [`docs/modules/hospitality.md`](modules/hospitality.md); this is the
integration contract.

### `GET /api/v1/hospitality/menu`

The sellable menu: `item_id`, `item_code`, `name`, `description`, `category_id`, `price`,
`currency_code`. Cursor-paginated. `?category_id=` is how a property scopes it — Atlas ships no
menu-membership entity, so the site passes the id of the `MENU` item category the hospitality
industry template seeds. **Unfiltered it returns every active item in the tenant, ingredients
included.** An item with no applicable price is listed with `price: null` and is **not orderable**;
that is a misconfiguration surfaced rather than hidden.

```
Cache-Control: private, max-age=60, stale-while-revalidate=600, stale-if-error=86400
```

**There is no ETag on this endpoint, on purpose (D-073).** A collection validator over `Item` cannot
see a reprice — prices live in another table — so it would answer 304 and pin yesterday's price
forever. Staleness is bounded instead: the menu is fresh for 60 s, usable for 10 more minutes while
a revalidation runs, and usable for a **day** if Atlas is unreachable, because a restaurant with no
ERP still has a menu and serving an empty one is lost revenue.

### `GET /api/v1/hospitality/menu/availability`

The 86 board — every item the kitchen has said something about, and **nothing else**. Anything
absent from it is available. Each row carries `state` (`AVAILABLE` / `LIMITED` / `EIGHTY_SIXED`),
`remaining_qty`, `available_until`, `reason` and `source`; the page carries `as_of`, the single
instant every row was resolved against.

```
Cache-Control: no-cache, must-revalidate, stale-if-error=300
ETag: W/"…"          # send it back as If-None-Match; a 304 costs Atlas one query
```

Revalidate on **every** request — a stale "available" sells a dish that is gone. The validator moves
when a dish is 86'd, un-86'd, a countdown ticks, a countdown hits zero, **and when a time-boxed 86
lapses** (lapsing changes the answer without changing a row, so the tag carries a lapsed-count
component). It deliberately does **not** move when a new dish is created or a price changes —
neither changes this board.

`stale-if-error` is short and fails **open**: showing an unavailable dish is a normal restaurant
apology; showing nothing is not.

**The board fits one page by contract** — Atlas serves up to `MAX_LIMIT` (200) overrides and the
endpoint takes no `limit`. Past 200 simultaneous overrides `next_cursor` is non-null and the client
**must** follow it; a client that ignores it reads a truncated board as "everything else is
available". Two pages are also two snapshots, which is what `as_of` makes visible.

### `POST /api/v1/hospitality/orders`

```http
POST /api/v1/hospitality/orders
Authorization: Bearer atk_…
Idempotency-Key: 5f2c9e10-…          # REQUIRED
Content-Type: application/json

{"table_code": "12", "guest_count": 2, "notes": null,
 "lines": [{"item_id": "8f4e…", "quantity": "2", "seat_number": 1, "notes": "no basil"}]}
```

Response `201`:

```json
{"ticket_id": "…", "ticket_number": "TKT-2026-000001", "status": "SENT_TO_KITCHEN",
 "opened_date": "2026-08-14", "total_amount": "37.000000", "currency_code": "USD"}
```

The order is priced server-side, opened as a check and **fired to the kitchen in the same request**,
so an 86'd dish comes back `422 hospitality.item_unavailable` rather than reaching a kitchen that
cannot make it.

**Five rules the client must follow.**

1. **`total_amount` is authoritative.** Display it before payment. Never a total the site computed
   from a cached menu price — the menu may be up to 60 s (plus its stale window) old, and Atlas
   prices the order at request time. It is a decimal **string** (D-015), like every money field in
   the API, and it is **pre-tax** (v1 puts no tax on a check).
2. **The body must carry no price.** `unit_price` is resolved from the price list; unknown fields
   are rejected (`422`) rather than silently ignored, so a site that thinks it set a price finds out
   immediately.
3. **On `409 idempotency.in_progress`, retry later with the SAME key.** Minting a new key on a 409
   is exactly how the duplicate order the mechanism exists to prevent gets created. A replay must
   also send the **byte-identical** body — re-serialising with different key order or whitespace is
   `422 idempotency.key_reuse`.
4. **Use a fresh key per order.** A key is scoped to its endpoint *and* its request target (D-071);
   reusing one across two orders is `422 idempotency.key_reuse`, never a silent replay.
5. **Depletion is not done when the 201 returns.** Ingredients are issued by a background job
   (D-072). The response means the kitchen has the check, not that stock has moved; a failure shows
   up at `GET /api/v1/jobs?status=FAILED` naming the ticket, and the ticket document's D-012 chain
   links to the stock moves once they post.

Refusals are the ordinary error envelope: `422 hospitality.item_not_priced` (no active price list
prices the item today, or its only price is in a currency that is not the tenant's functional one),
`422 hospitality.item_unavailable` (86'd, or a countdown with fewer portions left than ordered),
`401` for a bad key, `403` if the key's scopes do not cover the route, `429` from the edge limiter.


## The reservation contract

The same website, a **different key**: scope it to `hospitality.reservation.book` and **nothing
else**. That key can check availability, book, and cancel on a guest's behalf. It deliberately
cannot read the book — `hospitality.reservation.read` returns every guest's name and contact detail
for the night, and a leaked website key must not be a guest list (D-069's narrowing rule; the API
enforces it, this is just the reason).

**Whose booking is whose is your problem, not Atlas's.** Atlas exposes tenant-scoped operations and
trusts the caller to have authenticated its guest. Guest identity, notification (email/SMS) and
guest-facing cancel links are all the website's, exactly as Q1 draws the boundary.

**All times are UTC instants.** `slot_start` must carry an offset — a naive datetime is rejected
(`422`), because the slot instant is half of the pacing counter's key and guessing at an offset
silently splits one slot's counter in two. `service_date` is the **business date** the service
belongs to, which for a service running past midnight is the day it OPENED, not the calendar date of
the slot.

### `GET /api/v1/hospitality/reservation-availability?service_date=&party_size=`

The whole day's grid for **that party size**, one boolean per 15-minute slot:

```json
{"service_date": "2026-08-16", "party_size": 4,
 "slots": [{"slot_start": "2026-08-16T11:00:00Z", "bookable": true},
           {"slot_start": "2026-08-16T11:15:00Z", "bookable": false}]}
```

```
Cache-Control: no-cache, must-revalidate, stale-if-error=300
ETag: W/"…"
```

Revalidated on **every** request, like the 86 board and for the same reason: a stale "bookable"
sells a table that is gone. Send `If-None-Match` and expect `304` when nothing has moved — the
validator tracks both the day's bookings and the property's capacity settings, so widening capacity
invalidates it even though no booking changed. `party_size` is echoed back because `bookable` is
meaningless without it; never render a cached grid against a different party.

A party the property does not seat is `422 hospitality.party_size_not_accepted` rather than a grid
of `false`, and a date outside the booking window is `422 hospitality.outside_booking_window`. The
window's floor is the earliest service whose hours have **not yet closed**, not the UTC calendar
date: a service running past UTC midnight (22:00–05:00 UTC is an ordinary Americas dinner) keeps
answering for its own `service_date` while it is still being run.

### `POST /api/v1/hospitality/table-reservations`

```http
POST /api/v1/hospitality/table-reservations
Authorization: Bearer atk_…
Idempotency-Key: 9d1a4c77-…          # REQUIRED
Content-Type: application/json

{"service_date": "2026-08-16", "slot_start": "2026-08-16T19:00:00Z", "party_size": 4,
 "guest_name": "Okonkwo", "guest_contact": "+44 7700 900000", "notes": "window table if possible"}
```

Response `201`:

```json
{"id": "…", "document_id": "…", "reservation_number": "RSV-2026-000001", "status": "CONFIRMED",
 "service_date": "2026-08-16", "slot_start": "2026-08-16T19:00:00Z", "party_size": 4,
 "guest_name": "Okonkwo", "guest_contact": "+44 7700 900000", "notes": "…", "ticket_id": null}
```

**Four rules the client must follow.**

1. **`CONFIRMED` is final — there is no pending state to poll.** Passing the pacing gate *is* the
   confirmation, so the 201 is the answer. Nothing will later downgrade it.
2. **A full slot is a NORMAL answer, not an error.** `422 hospitality.slot_full` carries
   `details.limit` (`covers` or `parties`), `requested`, `available`, **and `alternatives`** — the
   other slots bookable for this party on this date, in the same `…Z` spelling the grid uses. Offer
   them; do not re-fetch the grid.
3. **On `409 idempotency.in_progress`, retry later with the SAME key**, and send the byte-identical
   body. Minting a new key on a 409 is how a guest ends up holding two tables. Use a **fresh** key
   per booking: a key is scoped to its endpoint and its request target (D-071).
4. **Unknown fields are rejected (`422`), not ignored** — including `table_code`. Which table a party
   sits at is decided by a human at seating and lives on their check, so it is not yours to set.

### `POST /api/v1/hospitality/table-reservations/{id}/cancel`

Returns the reservation at `CANCELLED`. **Before** the slot starts this gives the covers back to the
night; at or after it, the cancellation is recorded and the counter is untouched, because there is
nobody left to resell to. Refused with `409 hospitality.reservation_not_transitionable` once the
party has been SEATED (they are at the table; the correction wanted then is on their check) and for
a second cancel of the same booking. No idempotency key: it creates no document, and that same 409
already answers a replay. An unknown id is `404 hospitality.reservation_not_found`.
