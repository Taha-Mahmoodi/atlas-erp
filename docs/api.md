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

### 2. The secret is shown once

The `201` body is the key's record plus one extra field, `key`, holding the full string — `atk_<your tenant slug>_<secret>`. **This is the only time it exists anywhere.** Only its SHA-256 is stored, so a lost key is re-issued, never recovered.

Everything else stays readable from `GET /api/v1/admin/api-keys` (newest first, cursor-paginated, revoked and expired keys included). It never returns the secret or its digest, and `prefix` is only the non-secret half — `atk_<your tenant slug>`, identical for every key you own. Tell keys apart by `name`, which is why it is required.

### 3. Send it

As an ordinary bearer token:

```
Authorization: Bearer atk_acme_kJ2f…
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
