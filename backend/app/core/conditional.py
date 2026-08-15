"""Conditional GETs on slow-changing reference data — collection-level weak ETags (D-035).

PERFORMANCE §3 requires ``ETag/If-None-Match`` on slow-changing reference collections (chart of
accounts, currencies, tax codes, fiscal calendar, posting defaults). This is a justified core
flat file (the same precedent as core/pagination.py): the validator machinery is cross-cutting,
mentions no business concept, and every reference endpoint composes it the same way.

**Why collection-level, not row-level.** A row-level ETag would validate one entity; a list
endpoint returns a *page* of a collection, and the cheapest correct validator for "has anything in
this collection changed?" is a single aggregate ``SELECT COUNT(id), MAX(updated_at)`` over the
tenant's rows. Any insert moves the count; any update moves ``MAX(updated_at)`` (TimestampMixin's
``onupdate``); a delete moves the count (and usually the max). So the pair ``(count, max_updated)``
is a sound WEAK validator for the whole collection. The cost: any change to the collection
invalidates *every* page's cached validator — acceptable for small reference sets, which is exactly
the data this is applied to (PERFORMANCE §3 scopes it to reference data only, never transactional
lists). Deletes that leave count unchanged are impossible for a pure delete; a delete-then-insert
in the same instant could in principle pin both count and max, so we additionally guard correctness
with the request fingerprint below — but for the data this covers the (count, max) pair is the
dominant signal.

**Tenant component (D-007).** The aggregate select references the model's columns
(``func.count(model.id)``), so the ``do_orm_execute`` tenancy listener engages and scopes the
COUNT/MAX to the current tenant automatically (verified: a ``func`` aggregate over mapped columns
carries the mapper, so ``all_mappers`` detects it). The tenant id is *also* baked into the ETag
string as a short component, so even if two tenants happened to hold the same (count, max) the
validators differ — a cross-tenant 304 is impossible by construction, belt-and-suspenders over the
already tenant-scoped aggregate.

**Request fingerprint (the key correctness point).** The ETag represents the *whole collection's*
version, not one page. A naive collection-level validator would let a client that cached page 2
receive a 304 for a request for page 5 (same collection, unchanged) and then render the wrong
slice. To prevent that, the request's cursor + limit + filters are hashed into the ETag, so the
validator is unique per (collection-version, page-request). A 304 can therefore only ever be served
for the *identical* page request whose body the client already holds.

**Format.** ``W/"<count>-<max_updated_at_micros>-<tenant8>-<reqfingerprint>"`` — a weak validator
(``W/`` prefix) because two byte-different but semantically-equal page renderings (e.g. ordering
ties) should still match. Empty collection → ``W/"0--<tenant8>-<reqfingerprint>"`` (a stable
``max`` component of empty string), which still changes the moment the first row is inserted.
"""

from collections.abc import Awaitable, Callable

import sqlalchemy as sa
from fastapi import Request, Response
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.tenancy import get_current_tenant_id

# 304 carries no body; only the validator header rides back so the client can revalidate again.
NOT_MODIFIED_STATUS = 304


def _tenant_component() -> str:
    """Short, stable tenant marker for the ETag. The aggregate is already tenant-scoped by the
    D-007 listener; this makes a cross-tenant validator collision impossible even in theory, since
    two tenants' validators differ in this component regardless of their (count, max). Reads the
    request's tenant from the ContextVar (set by core/deps.get_current_user)."""
    tenant_id = get_current_tenant_id()
    # get_current_tenant_id is fail-closed and only returns None under system_context, which a
    # tenant reference endpoint never runs under; guard anyway so the helper is total.
    return tenant_id.hex[:8] if tenant_id is not None else "system"


async def collection_etag(
    session: AsyncSession,
    model: type,
    *extra_filters: sa.ColumnElement[bool],
    request_fingerprint: str = "",
    extra_components: tuple[sa.ColumnElement[object], ...] = (),
) -> str:
    """Compute a WEAK collection validator from ONE cheap aggregate query (D-035).

    ``SELECT COUNT(model.id), MAX(model.updated_at)`` — tenant-scoped automatically by the D-007
    ``do_orm_execute`` listener (the aggregate references the model's mapped columns, so the
    tenant predicate is injected). ``extra_filters`` narrow the collection to the same rows the
    list endpoint returns (e.g. a ``fiscal_year_id`` filter), so the validator tracks the visible
    slice, not the whole table. ``request_fingerprint`` (cursor+limit+filters of the actual
    request) is folded into the returned tag so a 304 can never serve a different page slice.

    ``extra_components`` are ADDITIONAL aggregate expressions selected in the SAME statement and
    folded into the tag, for the one collection whose answer can change without any row changing:
    a validator is only sound while ``(count, max_updated)`` covers every input to the response
    body, and a collection whose read applies a TIME predicate (hospitality's lazily-expiring 86
    board) has an input the clock moves and no write touches. Such a collection passes an aggregate
    that tracks that input — e.g. how many rows have already lapsed — and pays nothing extra for
    it, because it rides the aggregate select that was already being issued. Every other caller
    passes none and gets the byte-identical tag it got before this parameter existed.

    The returned string is the full weak ETag ready for the ``ETag`` header / ``If-None-Match``
    comparison: ``W/"<count>-<max_micros>[-<extra>...]-<tenant8>-<reqfingerprint>"``.
    """
    stmt = sa.select(sa.func.count(model.id), sa.func.max(model.updated_at), *extra_components)
    for clause in extra_filters:
        stmt = stmt.where(clause)
    count, max_updated, *extras = (await session.execute(stmt)).one()

    # Microsecond epoch keeps the component compact and monotonic; empty collection → "" so the
    # validator is stable for an empty set yet flips the moment the first row lands (count 0->1).
    max_component = (
        "" if max_updated is None else str(int(max_updated.timestamp() * 1_000_000))
    )
    extra_component = "".join(f"-{value}" for value in extras)
    return (
        f'W/"{count}-{max_component}{extra_component}'
        f'-{_tenant_component()}-{request_fingerprint}"'
    )


def _normalize_tag(raw: str) -> str:
    """Strip a leading weak marker so weak/strong forms of the same tag compare equal. Per RFC
    7232 the weak-comparison function ignores the ``W/`` prefix; our validators are always weak,
    but a client may echo the value with or without it, so normalize both sides."""
    raw = raw.strip()
    if raw.startswith("W/"):
        raw = raw[2:]
    return raw


def check_not_modified(request: Request, etag: str) -> bool:
    """True when the client's ``If-None-Match`` satisfies ``etag`` (RFC 7232 weak comparison).

    Handles the ``*`` value (matches any existing representation → 304 whenever the resource
    exists) and a comma-separated list of candidate tags. Comparison is weak: the ``W/`` prefix is
    ignored on both sides. A missing/blank header → False (the endpoint then serves a normal 200).
    """
    header = request.headers.get("if-none-match")
    if not header:
        return False
    candidates = [part.strip() for part in header.split(",") if part.strip()]
    if "*" in candidates:
        return True
    target = _normalize_tag(etag)
    return any(_normalize_tag(candidate) == target for candidate in candidates)


async def conditional_response[T](
    request: Request,
    response: Response,
    etag: str,
    builder: Callable[[], Awaitable[T]],
) -> T | Response:
    """Conditional-GET epilogue for a reference list endpoint (D-035).

    Given the already-computed collection ``etag``: if the client's ``If-None-Match`` matches,
    return a bare ``304`` carrying ONLY the ``ETag`` header and NO body — and crucially WITHOUT
    awaiting ``builder``, so the expensive full-page query never runs on the 304 path (this is what
    makes a conditional request cheaper than the unconditional one). Otherwise set the ``ETag``
    header on the real response and return ``await builder()`` (the ``Page`` payload).

    Returning a starlette ``Response`` directly bypasses the route's ``response_model``, so FastAPI
    does not try to validate the empty 304 body against ``Page[T]`` (verified by a test).
    """
    if check_not_modified(request, etag):
        return Response(status_code=NOT_MODIFIED_STATUS, headers={"ETag": etag})
    response.headers["ETag"] = etag
    return await builder()


def request_fingerprint(cursor: str | None, limit: int, *filter_parts: object) -> str:
    """Stable per-request fingerprint folded into the collection ETag so a 304 can only ever be
    served for the IDENTICAL page request (D-035). Reuses the pagination filter-fingerprint hash so
    the cursor/limit/filter identity matches what ``paginate`` already keys cursors on — one source
    of truth for "which slice of the collection is this request asking for"."""
    # Imported lazily: core/pagination imports core/schemas which is heavy; keeping the import here
    # avoids any import-order coupling and this helper is called per request, not at module load.
    from app.core.pagination import filter_fingerprint

    return filter_fingerprint(cursor, limit, *filter_parts)


__all__ = [
    "check_not_modified",
    "collection_etag",
    "conditional_response",
    "request_fingerprint",
]
