"""D-014 keyset (seek) pagination against a real tenant-scoped model (TenantSetting).

Proves: forward paging with no overlap and no gaps; next_cursor null on the last page; a
tampered/foreign cursor → 400 pagination.invalid_cursor; tiebreaker stability across rows with an
identical sort value; the limit cap; and ascending/descending ordering correctness.
"""

import uuid
from datetime import UTC, datetime

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.exceptions import ValidationFailedError
from app.core.pagination import (
    DEFAULT_LIMIT,
    MAX_LIMIT,
    OrderKey,
    SortDirection,
    cursor_params,
    decode_cursor,
    encode_cursor,
    filter_fingerprint,
    paginate,
)
from app.core.tenancy import tenant_context
from app.modules.admin.models import TenantSetting


async def _seed_settings(
    session: AsyncSession,
    tenant_id: uuid.UUID,
    keys: list[str],
    *,
    created_at: datetime | None = None,
) -> None:
    with tenant_context(tenant_id):
        for key in keys:
            setting = TenantSetting(key=key, value={"k": key})
            if created_at is not None:
                setting.created_at = created_at
            session.add(setting)
        await session.commit()


async def test_forward_paging_no_overlap_no_gaps_and_terminates(
    db_session: AsyncSession, tenant_a: uuid.UUID
) -> None:
    keys = [f"k{i:02d}" for i in range(10)]
    await _seed_settings(db_session, tenant_a, keys)
    order = [OrderKey(TenantSetting.key, SortDirection.ASC)]

    seen: list[str] = []
    cursor: str | None = None
    pages = 0
    with tenant_context(tenant_a):
        while True:
            page = await paginate(
                db_session,
                select(TenantSetting),
                order_by=order,
                pk=TenantSetting.id,
                cursor=cursor,
                limit=3,
            )
            pages += 1
            seen.extend(item.key for item in page.items)
            assert len(page.items) <= 3
            if page.next_cursor is None:
                break
            cursor = page.next_cursor
            assert pages < 20  # guard against an infinite loop

    # Every row exactly once, in ascending order, and the last page terminated (next_cursor null).
    assert seen == sorted(keys)
    assert len(seen) == len(set(seen)) == 10


async def test_last_page_has_null_next_cursor_when_exactly_filled(
    db_session: AsyncSession, tenant_a: uuid.UUID
) -> None:
    # Exactly `limit` rows: the limit+1 probe finds no extra row, so next_cursor is null.
    await _seed_settings(db_session, tenant_a, ["a", "b", "c"])
    order = [OrderKey(TenantSetting.key, SortDirection.ASC)]
    with tenant_context(tenant_a):
        page = await paginate(
            db_session,
            select(TenantSetting),
            order_by=order,
            pk=TenantSetting.id,
            limit=3,
        )
    assert [item.key for item in page.items] == ["a", "b", "c"]
    assert page.next_cursor is None


async def test_descending_order_is_respected(
    db_session: AsyncSession, tenant_a: uuid.UUID
) -> None:
    keys = ["a", "b", "c", "d", "e"]
    await _seed_settings(db_session, tenant_a, keys)
    order = [OrderKey(TenantSetting.key, SortDirection.DESC)]

    seen: list[str] = []
    cursor: str | None = None
    with tenant_context(tenant_a):
        while True:
            page = await paginate(
                db_session,
                select(TenantSetting),
                order_by=order,
                pk=TenantSetting.id,
                cursor=cursor,
                limit=2,
            )
            seen.extend(item.key for item in page.items)
            if page.next_cursor is None:
                break
            cursor = page.next_cursor
    assert seen == sorted(keys, reverse=True)


async def test_tiebreaker_keeps_rows_with_equal_sort_value_stable(
    db_session: AsyncSession, tenant_a: uuid.UUID
) -> None:
    # All rows share one created_at, so the sort column ties on every row and ONLY the id
    # tiebreaker orders them. Paging must still return every row exactly once (no skips/dupes).
    same_instant = datetime(2026, 1, 1, 12, 0, 0, tzinfo=UTC)
    keys = [f"dup{i:02d}" for i in range(12)]
    await _seed_settings(db_session, tenant_a, keys, created_at=same_instant)
    order = [OrderKey(TenantSetting.created_at, SortDirection.ASC)]

    seen: list[str] = []
    cursor: str | None = None
    with tenant_context(tenant_a):
        while True:
            page = await paginate(
                db_session,
                select(TenantSetting),
                order_by=order,
                pk=TenantSetting.id,
                cursor=cursor,
                limit=5,
            )
            seen.extend(item.key for item in page.items)
            if page.next_cursor is None:
                break
            cursor = page.next_cursor

    assert sorted(seen) == sorted(keys)
    assert len(seen) == len(set(seen)) == 12


async def test_tampered_or_foreign_cursor_raises_invalid_cursor(
    db_session: AsyncSession, tenant_a: uuid.UUID
) -> None:
    await _seed_settings(db_session, tenant_a, ["a", "b", "c", "d"])
    order = [OrderKey(TenantSetting.key, SortDirection.ASC)]
    with tenant_context(tenant_a):
        first = await paginate(
            db_session,
            select(TenantSetting),
            order_by=order,
            pk=TenantSetting.id,
            limit=2,
        )
        assert first.next_cursor is not None

        # Garbage cursor.
        try:
            await paginate(
                db_session,
                select(TenantSetting),
                order_by=order,
                pk=TenantSetting.id,
                cursor="not-a-valid-cursor!!!",
                limit=2,
            )
            raise AssertionError("expected invalid_cursor")
        except ValidationFailedError as exc:
            assert exc.code == "pagination.invalid_cursor"

        # A valid cursor from one SORT replayed under a different sort is rejected (fingerprint
        # mismatch) — the same protection covers a different filter set.
        try:
            await paginate(
                db_session,
                select(TenantSetting),
                order_by=[OrderKey(TenantSetting.key, SortDirection.DESC)],
                pk=TenantSetting.id,
                cursor=first.next_cursor,
                limit=2,
            )
            raise AssertionError("expected invalid_cursor for changed sort")
        except ValidationFailedError as exc:
            assert exc.code == "pagination.invalid_cursor"


async def test_cursor_carries_filter_fingerprint(
    db_session: AsyncSession, tenant_a: uuid.UUID
) -> None:
    await _seed_settings(db_session, tenant_a, ["a", "b", "c", "d"])
    order = [OrderKey(TenantSetting.key, SortDirection.ASC)]
    fp = filter_fingerprint("status", "ACTIVE")
    with tenant_context(tenant_a):
        page = await paginate(
            db_session,
            select(TenantSetting),
            order_by=order,
            pk=TenantSetting.id,
            limit=2,
            filters=fp,
        )
        assert page.next_cursor is not None
        # A cursor minted under one filter fingerprint cannot be replayed under a different one.
        try:
            await paginate(
                db_session,
                select(TenantSetting),
                order_by=order,
                pk=TenantSetting.id,
                cursor=page.next_cursor,
                limit=2,
                filters=filter_fingerprint("status", "ARCHIVED"),
            )
            raise AssertionError("expected invalid_cursor for changed filter")
        except ValidationFailedError as exc:
            assert exc.code == "pagination.invalid_cursor"


def test_cursor_params_clamps_limit_to_max_and_floor() -> None:
    assert cursor_params(limit=5000).limit == MAX_LIMIT
    assert cursor_params(limit=0).limit == 1
    assert cursor_params().limit == DEFAULT_LIMIT
    assert cursor_params(cursor="abc", limit=10) == cursor_params("abc", 10)


def test_cursor_codec_round_trips_and_rejects_version_mismatch() -> None:
    spec = "key:asc,id:asc"
    fp = filter_fingerprint()
    cursor = encode_cursor(["m", str(uuid.uuid4())], spec, fp)
    assert decode_cursor(cursor, spec, fp)[0] == "m"
    # A different sort spec is a mismatch.
    try:
        decode_cursor(cursor, "key:desc,id:asc", fp)
        raise AssertionError("expected invalid_cursor")
    except ValidationFailedError as exc:
        assert exc.code == "pagination.invalid_cursor"


async def test_datetime_desc_ties_wider_than_page_terminate_without_dupes(
    db_session: AsyncSession, tenant_a: uuid.UUID
) -> None:
    """Regression #34: server-default-era timestamps broke cursor equality on SQLite —
    a DESC DateTime sort with ties wider than the page size returned the first page
    forever. With Python-written canonical timestamps (TimestampMixin default=utcnow),
    the equality arm matches and the PK tiebreaker advances the cursor. Walk every
    page; assert termination, full coverage, and zero duplicates."""
    shared = datetime(2026, 6, 12, 12, 0, 0, tzinfo=UTC)
    with tenant_context(tenant_a):
        for i in range(7):
            setting = TenantSetting(key=f"tie-{i}", value={"i": i})
            setting.created_at = shared
            setting.updated_at = shared
            db_session.add(setting)
        await db_session.commit()

        order = [OrderKey(TenantSetting.created_at, SortDirection.DESC)]
        seen: list[uuid.UUID] = []
        cursor = None
        for _ in range(10):  # 7 rows / page 3 => must finish in 3 pages
            page = await paginate(
                db_session,
                select(TenantSetting),
                order_by=order,
                pk=TenantSetting.id,
                cursor=cursor,
                limit=3,
            )
            seen.extend(row.id for row in page.items)
            cursor = page.next_cursor
            if cursor is None:
                break
        assert cursor is None, "pagination did not terminate (#34 loop)"
        assert len(seen) == 7
        assert len(set(seen)) == 7, "duplicate rows across pages (#34)"


async def test_timestamps_are_python_written_with_microsecond_format(
    db_session: AsyncSession, tenant_a: uuid.UUID
) -> None:
    """Regression #34: no SQLAlchemy write may fall through to the DDL CURRENT_TIMESTAMP
    default (second-precision on SQLite). A fresh ORM row's created_at must carry the
    Python-written value (microsecond resolution survives the round-trip)."""
    with tenant_context(tenant_a):
        setting = TenantSetting(key="fmt-probe", value={})
        db_session.add(setting)
        await db_session.commit()
        await db_session.refresh(setting)
    # The DDL default would store second precision; utcnow() practically never lands on
    # a whole second. Probabilistic but deterministic-enough: retry once if unlucky.
    if setting.created_at.microsecond == 0:
        with tenant_context(tenant_a):
            probe = TenantSetting(key="fmt-probe-2", value={})
            db_session.add(probe)
            await db_session.commit()
            await db_session.refresh(probe)
        assert probe.created_at.microsecond != 0
    else:
        assert setting.created_at.microsecond != 0
