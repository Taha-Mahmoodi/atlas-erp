"""D-014 keyset (seek) pagination — never OFFSET.

Cursor browsing is O(page) at any depth and stable under concurrent inserts (the ERP norm for
ledger/list browsing). Every list orders by a whitelisted sort column plus the PK ``id`` as a
mandatory unique tiebreaker (``ORDER BY created_at DESC, id DESC``), fetches ``limit + 1`` rows,
and emits ``next_cursor`` from the last RETURNED row only when the extra row arrived.

**Cursor.** ``base64url(JSON)`` of ``{"v":1, "k":[last sort values..., last id], "s": sort-spec,
"q": filter fingerprint}`` — opaque to clients, validated server-side. ``v``, ``s`` and ``q`` must
match the current request (a cursor minted for one query/sort/filter can't be replayed on
another) → 400 ``pagination.invalid_cursor`` on any mismatch or tamper.

**Seek predicate.** Written in the EXPANDED portable OR-form
``col0 < k0 OR (col0 = k0 AND col1 < k1) OR (... AND id < kN)`` (directions flipped per column for
ASC). D-014 mandates this expansion because SQLite lacks MIXED-direction row-value comparison —
``(a, b) > (x, y)`` only works when every column sorts the same way, and our lists mix ASC/DESC
freely — so the expansion is the only form correct on BOTH engines (verified: this project's
aiosqlite, 3.53, DOES support uniform-direction row-values, but the expanded form is used
unconditionally so a mixed-direction sort is never silently wrong).

**Placement deviation.** D-014's letter puts ``paginate`` in ``core/db.py`` and the cursor codec
in ``core/schemas.py``. The keyset machinery (codec + fingerprint + expanded predicate +
CursorParams) is substantial and cross-cutting, so it gets its own flat core file per STRUCTURE
§8.5 ("one concept per file") — a justified core addition recorded in DECISIONS.md, the same way
core/money.py and core/custom_fields.py were. The ``Page`` envelope stays in core/schemas.py.
"""

import base64
import binascii
import hashlib
import json
import uuid
from dataclasses import dataclass
from datetime import date, datetime
from decimal import Decimal
from enum import StrEnum
from typing import Any

import sqlalchemy as sa
from sqlalchemy import Select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import InstrumentedAttribute

from app.core.exceptions import ValidationFailedError
from app.core.schemas import Page

DEFAULT_LIMIT = 50
MAX_LIMIT = 200
_CURSOR_VERSION = 1


class SortDirection(StrEnum):
    ASC = "asc"
    DESC = "desc"


@dataclass(frozen=True)
class OrderKey:
    """One whitelisted sort column + direction. ``paginate`` always appends the PK as the final
    tiebreaker, so a list declares only its business sort columns (e.g. created_at DESC)."""

    column: InstrumentedAttribute[Any]
    direction: SortDirection = SortDirection.ASC

    @property
    def name(self) -> str:
        return self.column.key


def _sort_spec(order_keys: list[OrderKey]) -> str:
    """Stable string identity of the sort (``'created_at:desc,id:asc'``), embedded in the cursor
    so a cursor minted under one ordering is rejected if the request's ordering changed."""
    return ",".join(f"{key.name}:{key.direction.value}" for key in order_keys)


def _encode_value(value: Any) -> Any:
    """Serialize a sort-key value to a JSON-safe, round-trippable form. datetimes/dates go to ISO
    strings, Decimals to strings (exact, consistent with D-015), UUIDs to str; primitives pass."""
    if isinstance(value, datetime | date):
        return value.isoformat()
    if isinstance(value, Decimal):
        return str(value)
    if isinstance(value, bool | int | float | str) or value is None:
        return value
    return str(value)


def encode_cursor(key_values: list[Any], sort_spec: str, filter_fingerprint: str) -> str:
    """base64url(JSON) of the last row's key tuple + the sort/filter fingerprints (D-014)."""
    payload = {
        "v": _CURSOR_VERSION,
        "k": [_encode_value(value) for value in key_values],
        "s": sort_spec,
        "q": filter_fingerprint,
    }
    raw = json.dumps(payload, separators=(",", ":"), sort_keys=True).encode("utf-8")
    return base64.urlsafe_b64encode(raw).decode("ascii")


def decode_cursor(cursor: str, sort_spec: str, filter_fingerprint: str) -> list[Any]:
    """Decode and validate a cursor, returning its key tuple. Any tamper, malformed payload, wrong
    version, or a sort/filter fingerprint that does not match the CURRENT request raises 400
    ``pagination.invalid_cursor`` — a cursor cannot be replayed on a different query (D-014)."""
    try:
        raw = base64.urlsafe_b64decode(cursor.encode("ascii"))
        payload = json.loads(raw)
    except (binascii.Error, ValueError, UnicodeDecodeError) as exc:
        raise _invalid_cursor() from exc
    if not isinstance(payload, dict):
        raise _invalid_cursor()
    if (
        payload.get("v") != _CURSOR_VERSION
        or payload.get("s") != sort_spec
        or payload.get("q") != filter_fingerprint
        or not isinstance(payload.get("k"), list)
    ):
        raise _invalid_cursor()
    return payload["k"]


def _invalid_cursor() -> ValidationFailedError:
    return ValidationFailedError(
        message="The pagination cursor is invalid for this query",
        code="pagination.invalid_cursor",
    )


def filter_fingerprint(*parts: Any) -> str:
    """sha256-prefix of normalized filter parts (D-014). Routers pass whatever WHERE inputs scope
    the list (status, date range, search term…); a different filter set yields a different
    fingerprint, so a cursor from one filtered view can't bleed into another. Empty parts → the
    fingerprint of an empty filter set, still stable."""
    canonical = json.dumps([_encode_value(part) for part in parts], separators=(",", ":"))
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()[:16]


def _coerce_key_value(column: InstrumentedAttribute[Any], value: Any) -> Any:
    """Coerce a decoded cursor value back to the column's Python type so the seek comparison binds
    correctly on both engines. datetimes/dates and Decimals were ISO/str-encoded; the rest are
    JSON primitives that bind as-is (SQLAlchemy adapts UUID/str columns from the str form)."""
    python_type = getattr(column.type, "python_type", None)
    if value is None or python_type is None or not isinstance(value, str):
        return value
    if python_type is datetime:
        return datetime.fromisoformat(value)
    if python_type is date:
        return date.fromisoformat(value)
    if python_type is Decimal:
        return Decimal(value)
    if python_type is uuid.UUID:
        # The PK tiebreaker is a UUID column; SQLAlchemy's Uuid type binds a uuid.UUID, not the
        # str it was cursor-encoded as, so re-parse it here (else the bind processor blows up).
        return uuid.UUID(value)
    return value


def _seek_predicate(order_keys: list[OrderKey], key_values: list[Any]) -> sa.ColumnElement[bool]:
    """Build the expanded OR-form seek predicate (D-014). For sort columns c0..cN with the values
    from the previous page's last row, the predicate selecting STRICTLY-AFTER rows is::

        cmp(c0)
        OR (c0 == v0 AND cmp(c1))
        OR (c0 == v0 AND c1 == v1 AND cmp(c2))
        ...

    where ``cmp`` is ``<`` for a DESC column and ``>`` for ASC. The PK tiebreaker is already the
    last OrderKey, so every distinct row is on exactly one side of the boundary — no skips, no
    duplicates, even when earlier sort columns tie. Expanded (not row-value) so mixed ASC/DESC is
    correct on SQLite too."""
    coerced = [
        _coerce_key_value(key.column, value)
        for key, value in zip(order_keys, key_values, strict=True)
    ]
    clauses: list[sa.ColumnElement[bool]] = []
    for i, key in enumerate(order_keys):
        equals = [order_keys[j].column == coerced[j] for j in range(i)]
        strict = (
            key.column > coerced[i]
            if key.direction is SortDirection.ASC
            else key.column < coerced[i]
        )
        clauses.append(sa.and_(*equals, strict))
    return sa.or_(*clauses)


def _apply_order(stmt: Select[Any], order_keys: list[OrderKey]) -> Select[Any]:
    return stmt.order_by(
        *(
            key.column.asc() if key.direction is SortDirection.ASC else key.column.desc()
            for key in order_keys
        )
    )


async def paginate[T](
    session: AsyncSession,
    stmt: Select[tuple[T]],
    *,
    order_by: list[OrderKey],
    pk: InstrumentedAttribute[Any],
    cursor: str | None = None,
    limit: int = DEFAULT_LIMIT,
    filters: str = "",
) -> Page[T]:
    """Keyset-paginate ``stmt`` and return a ``Page[T]`` (D-014). ``order_by`` is the whitelisted
    business sort; ``pk`` (the model's id) is appended as the mandatory unique tiebreaker so the
    cursor is stable. ``filters`` is the router's filter fingerprint (see
    :func:`filter_fingerprint`) baked into the cursor. The single generic helper module routers
    use — they never hand-roll keyset SQL.

    Fetches ``limit + 1`` rows; if the extra row arrives, the page is full and ``next_cursor`` is
    minted from the LAST returned row's sort-key tuple. The cursor (when present) is decoded and
    validated against this request's sort + filter fingerprint, then turned into the expanded-OR
    seek predicate that selects strictly-after rows."""
    if limit < 1:
        limit = 1
    keys = [*order_by, OrderKey(pk, SortDirection.ASC)]
    sort_spec = _sort_spec(keys)

    seek_stmt = stmt
    if cursor is not None:
        key_values = decode_cursor(cursor, sort_spec, filters)
        if len(key_values) != len(keys):
            raise _invalid_cursor()
        seek_stmt = seek_stmt.where(_seek_predicate(keys, key_values))

    seek_stmt = _apply_order(seek_stmt, keys).limit(limit + 1)
    rows = list((await session.execute(seek_stmt)).scalars().all())

    has_more = len(rows) > limit
    items = rows[:limit]
    next_cursor: str | None = None
    if has_more and items:
        last = items[-1]
        next_cursor = encode_cursor(
            [getattr(last, key.name) for key in keys], sort_spec, filters
        )
    return Page(items=items, next_cursor=next_cursor, limit=limit)


@dataclass(frozen=True)
class CursorParams:
    """Parsed ``?cursor=&limit=`` query params (D-014). ``limit`` is clamped to ``[1, MAX_LIMIT]``
    and defaults to ``DEFAULT_LIMIT``, so a client can never request an unbounded page. A router
    declares ``params: CursorParamsDep`` and forwards ``params.cursor`` / ``params.limit`` to
    :func:`paginate`."""

    cursor: str | None
    limit: int


def cursor_params(cursor: str | None = None, limit: int = DEFAULT_LIMIT) -> CursorParams:
    """FastAPI dependency parsing the cursor/limit query params with the max-limit cap (D-014)."""
    clamped = max(1, min(limit, MAX_LIMIT))
    return CursorParams(cursor=cursor, limit=clamped)


__all__ = [
    "DEFAULT_LIMIT",
    "MAX_LIMIT",
    "CursorParams",
    "OrderKey",
    "SortDirection",
    "cursor_params",
    "decode_cursor",
    "encode_cursor",
    "filter_fingerprint",
    "paginate",
]
