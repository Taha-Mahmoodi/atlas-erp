"""D-012 gapless per-tenant document numbering.

One half of the merged registry+numbering subsystem (the other half is core/docflow.py).
A document number is claimed INSIDE the business transaction that makes the document
permanent (drafts are numbered at posting). Because the counter increment and the
document insert commit or roll back together, gaplessness for committed documents falls
out of ACID with no burned-number reconciliation state (D-012 claim-timing rule).

The atomic claim is a single ``UPDATE core_number_sequences SET next_value = next_value + 1
... RETURNING next_value`` — one portable statement that takes the row lock and reads the
new counter in one round trip. RETURNING is verified working on the project's aiosqlite
(SQLite >= 3.35; this build runs 3.53) and on Postgres, so no SELECT-then-UPDATE fallback
is needed (D-012 sanctioned the fallback only if RETURNING were unavailable).

The ORM model lives HERE rather than in core/models.py: models.py is at ~273 lines and
adding the numbering + docflow entities would push it over the ~350-line soft cap, so the
D-012 entities sit in their concern files (numbering.py / docflow.py) — a placement the
PLAN sanctions explicitly and STRUCTURE §2 permits ("one concept per file": the sequence
concept lives with its claim logic). Noted in DECISIONS.md.
"""

import uuid
from datetime import UTC, date, datetime

import sqlalchemy as sa
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import Mapped, mapped_column

from app.core.exceptions import NotFoundError
from app.core.models import (
    Base,
    TenantMixin,
    TimestampMixin,
    UuidPKMixin,
    tenant_fk,
)


class NumberSequence(UuidPKMixin, TenantMixin, TimestampMixin, Base):
    """Per-tenant CONFIGURATION for one document kind's numbering (D-012).

    ``name`` is the namespaced sequence key (e.g. ``'finance.invoice'``); a claim formats
    ``{prefix}-{year?}-{padded value}`` (e.g. ``INV-2026-00001``). The running counters live
    in :class:`NumberSequenceCounter`, one row per year — see that class for why the year is
    part of the counter's identity rather than a stamp on this row. Not AuditMixin: sequence
    rows are infrastructure, not business state — auditing every increment would be noise
    (documented exclusion)."""

    __tablename__ = "core_number_sequences"
    __table_args__ = (
        # One sequence per (tenant, name). Explicit name: the D-022 convention keys on
        # column 0 (tenant_id) only and would collide with tenant_unique() below.
        sa.UniqueConstraint("tenant_id", "name", name="uq_core_number_sequences_tenant_id_name"),
        # UNIQUE(tenant_id, id) so other tenant-scoped tables could reference a sequence via
        # the composite-FK backstop if ever needed (D-007 item 4) — the counter table below
        # does exactly that.
        sa.UniqueConstraint("tenant_id", "id", name="uq_core_number_sequences_tenant_id"),
        tenant_fk("adm_tenants"),
    )

    name: Mapped[str] = mapped_column(sa.String(100), nullable=False)
    prefix: Mapped[str] = mapped_column(sa.String(20), nullable=False)
    padding: Mapped[int] = mapped_column(sa.Integer, nullable=False)
    year_reset: Mapped[bool] = mapped_column(
        sa.Boolean, nullable=False, default=False, server_default=sa.false()
    )


class NumberSequenceCounter(UuidPKMixin, TenantMixin, TimestampMixin, Base):
    """The running counter for one sequence in one year (D-012, issue #209).

    **The year is part of the counter's identity, not a stamp on the sequence.** The original
    shape kept one counter with a ``current_year`` and reset it whenever a claim's year differed
    from the stored one — which meant a document dated in a PAST year (entering December's paper
    invoice in January, a backdated restaurant check) reset the live counter to 1 and stamped it
    with the old year. Every later document in the real year then re-claimed a number that already
    existed and died on its table's unique index, with no in-app recovery. Refusing past-dated
    claims instead was rejected: backdating across a year boundary is ordinary, sanctioned
    accounting work, and the year segment exists precisely so each year carries its own series.

    So each year gets its own gapless counter, created on first claim (no rollover job, per D-012),
    and a claim can never disturb another year's numbers. A counter is born ABOVE the highest
    number that year already issued rather than at 1 (#216, see :func:`_create_counter`), so a
    year whose counter was lost — the state #209 left behind and migration 0051 could not see —
    resumes its series instead of re-issuing it. ``year`` is 0 — never NULL — for a
    sequence that does not year-reset, so the unique constraint below stays meaningful on both
    dialects (NULLs compare distinct in a UNIQUE index, which would let duplicate counters exist).
    """

    __tablename__ = "core_number_sequence_counters"
    __table_args__ = (
        sa.UniqueConstraint(
            "tenant_id",
            "sequence_id",
            "year",
            name="uq_core_number_sequence_counters_tenant_sequence_year",
        ),
        tenant_fk("adm_tenants"),
        # Composite FK (D-007 item 4): a counter can only ever point at a sequence in its own
        # tenant, enforced by the database rather than by the query author.
        sa.ForeignKeyConstraint(
            ["tenant_id", "sequence_id"],
            ["core_number_sequences.tenant_id", "core_number_sequences.id"],
            name="fk_core_number_sequence_counters_sequence",
        ),
    )

    sequence_id: Mapped[uuid.UUID] = mapped_column(sa.Uuid, nullable=False)
    # 0 for a sequence that does not year-reset; the calendar year otherwise.
    year: Mapped[int] = mapped_column(sa.Integer, nullable=False)
    # Next number to hand out. The atomic claim does next_value = next_value + 1 RETURNING
    # the post-increment value, so the FIRST claim of a counter at next_value=1 returns 1.
    next_value: Mapped[int] = mapped_column(
        sa.Integer, nullable=False, default=1, server_default=sa.text("1")
    )


# The counter bucket for a sequence that does not year-reset. A real year, never NULL, so the
# uniqueness of (tenant, sequence, year) holds on every dialect (see NumberSequenceCounter).
_NO_YEAR = 0


def _number_head(prefix: str, year: int | None) -> str:
    """Everything a number carries BEFORE its padded counter value: ``'INV-2026-'``, or
    ``'SO-'`` for a sequence that does not year-reset. One place knows the shape, so the
    formatter and the already-issued lookup below can never disagree about it."""
    return f"{prefix}-" if year is None else f"{prefix}-{year}-"


def _format_number(prefix: str, padding: int, value: int, year: int | None) -> str:
    """Render ``{prefix}-{year?}-{padded value}`` — the year segment is present only when
    the sequence year-resets (D-012). e.g. ('INV', 5, 1, 2026) -> 'INV-2026-00001'."""
    return f"{_number_head(prefix, year)}{str(value).zfill(padding)}"


async def ensure_sequence(
    session: AsyncSession,
    tenant_id: uuid.UUID,
    name: str,
    prefix: str,
    padding: int,
    year_reset: bool,
) -> NumberSequence:
    """Idempotent creator for provisioning/seed (D-012: year rollover and sequence setup
    need no job — rows are created on demand). Returns the existing row unchanged if the
    (tenant, name) sequence already exists, otherwise inserts the CONFIG row plus the counter
    for the CURRENT year.

    Opening the current year's counter here is a cost optimisation, not a rule: any year's
    counter is created on demand by its first claim (see :class:`NumberSequenceCounter`), but
    the overwhelmingly common case is documents dated in the year the tenant was provisioned,
    and having that row already there keeps the steady-state claim at exactly ONE statement.

    A Core insert is used (not an ORM add) so the tenant_id is set explicitly and the row
    is not subject to ORM tenant stamping — consistent with the D-007 sanction that core/
    numbering writes carry tenant_id explicitly. Callers run under the target tenant context
    or system_context (provisioning)."""
    existing = (
        await session.execute(
            select(NumberSequence).where(
                NumberSequence.tenant_id == tenant_id, NumberSequence.name == name
            )
        )
    ).scalar_one_or_none()
    if existing is not None:
        return existing

    sequence_id = uuid.uuid4()
    await session.execute(
        sa.insert(NumberSequence.__table__).values(
            id=sequence_id,
            tenant_id=tenant_id,
            name=name,
            prefix=prefix,
            padding=padding,
            year_reset=year_reset,
        )
    )
    await _create_counter(
        session,
        tenant_id,
        sequence_id,
        prefix,
        date.today().year if year_reset else None,
    )
    return (
        await session.execute(
            select(NumberSequence).where(
                NumberSequence.tenant_id == tenant_id, NumberSequence.name == name
            )
        )
    ).scalar_one()


async def claim_number(
    session: AsyncSession,
    tenant_id: uuid.UUID,
    sequence_name: str,
    *,
    on_date: date,
) -> str:
    """Atomically claim the next number for ``sequence_name`` and return the formatted
    string (D-012). The claim runs in the CALLER's transaction — the number is permanent
    only when that transaction commits, so a rollback returns the value to the pool and the
    next committed claim reuses it (gaplessness for committed documents).

    Mechanism — one portable atomic statement per claim:
    ``UPDATE core_number_sequence_counters SET next_value = next_value + 1
      WHERE tenant_id=:t AND sequence_id=:s AND year=:y RETURNING next_value`` — the RETURNING
    value is the post-increment counter; the row lock the UPDATE takes serializes concurrent
    claimers so two claims can never read the same number (verified on aiosqlite >= 3.35 and
    Postgres).

    ``on_date`` selects WHICH counter, and that is the whole year-reset rule: each year owns an
    independent counter, created on its first claim. A backdated document therefore numbers
    correctly in its own year and cannot disturb the current year's series — the failure mode
    issue #209 documents, where a past-dated claim reset the live counter and every subsequent
    document collided on its table's unique index.

    A Core UPDATE is used (bypasses the ORM tenant filter by design — core/ numbering is a
    D-007 sanctioned raw-SQL site with explicit tenant_id)."""
    sequence = (
        await session.execute(
            select(NumberSequence).where(
                NumberSequence.tenant_id == tenant_id, NumberSequence.name == sequence_name
            )
        )
    ).scalar_one_or_none()
    if sequence is None:
        raise NotFoundError(
            message=f"Number sequence '{sequence_name}' is not configured for this tenant",
            code="core.number_sequence_missing",
        )

    claim_year: int | None = on_date.year if sequence.year_reset else None
    bucket = claim_year if claim_year is not None else _NO_YEAR

    # ONE statement in the steady state: increment optimistically and only fall back to creating
    # the counter when the UPDATE matched nothing, which happens exactly once per year per
    # sequence. Checking existence first would have cost every claim an extra SELECT forever to
    # serve a case that arises once a year (it broke the depreciation run's query budget).
    claimed_value = await _increment(session, tenant_id, sequence.id, bucket)
    if claimed_value is None:
        await _create_counter(session, tenant_id, sequence.id, sequence.prefix, claim_year)
        claimed_value = await _increment(session, tenant_id, sequence.id, bucket)
    if claimed_value is None:  # pragma: no cover — the row was just created or already existed
        raise NotFoundError(
            message=f"Number sequence '{sequence_name}' lost its counter mid-claim",
            code="core.number_sequence_missing",
        )

    return _format_number(sequence.prefix, sequence.padding, claimed_value, claim_year)


async def _increment(
    session: AsyncSession, tenant_id: uuid.UUID, sequence_id: uuid.UUID, year: int
) -> int | None:
    """The atomic claim: ``UPDATE ... SET next_value = next_value + 1 RETURNING next_value``,
    returning the value claimed (the pre-increment counter), or None when this (sequence, year)
    has no counter row yet. The row lock the UPDATE takes is what serializes concurrent claimers,
    exactly as before — the counter simply lives in its own table now."""
    counters = NumberSequenceCounter.__table__
    row = (
        await session.execute(
            sa.update(counters)
            .where(
                counters.c.tenant_id == tenant_id,
                counters.c.sequence_id == sequence_id,
                counters.c.year == year,
            )
            .values(next_value=counters.c.next_value + 1)
            .returning(counters.c.next_value)
        )
    ).first()
    return None if row is None else row[0] - 1


async def _create_counter(
    session: AsyncSession,
    tenant_id: uuid.UUID,
    sequence_id: uuid.UUID,
    prefix: str,
    year: int | None,
) -> None:
    """Open this year's counter ABOVE anything that year already issued, without losing a race.

    ``year`` is the year segment of the number (None for a sequence that does not year-reset);
    the counter row itself buckets that as ``_NO_YEAR``.

    The counter opens at ``highest already issued + 1``, not at 1 (#216). A counter that this
    tenant lost — every tenant bitten by #209 lost one, because the corrupting claim overwrote
    the single old-schema counter's year and migration 0051 could only carry across the one year
    that survived — would otherwise be reborn at 1 and re-hand a number sitting on a committed
    document, which is the same unique-index 500 on the same document type that D-079 exists to
    remove. Seeding from the documents is what makes that unrecoverable state heal itself the
    moment the year is used again, rather than only in tenants an operator thought to inspect.

    The high-water mark is read INSIDE the insert (``INSERT ... SELECT``), not by a preceding
    SELECT, so this stays exactly ONE statement — D-079's cost argument survives untouched, and
    so does the depreciation run's query budget that rejected the extra-SELECT design there.

    A plain INSERT inside a SAVEPOINT rather than an upsert: ``ON CONFLICT`` spells differently on
    Postgres and SQLite and this module stays dialect-portable (D-012). The savepoint matters —
    on Postgres a raw IntegrityError poisons the whole transaction, and the caller's business
    writes are in it. The loser of a race rolls back only the nested block and re-runs the atomic
    increment against the winner's row.
    """
    counters = NumberSequenceCounter.__table__
    now = datetime.now(UTC)
    seed = select(
        sa.literal(uuid.uuid4(), sa.Uuid),
        sa.literal(tenant_id, sa.Uuid),
        sa.literal(sequence_id, sa.Uuid),
        sa.literal(_NO_YEAR if year is None else year, sa.Integer),
        _highest_issued(tenant_id, prefix, year) + 1,
        sa.literal(now, sa.DateTime(timezone=True)),
        sa.literal(now, sa.DateTime(timezone=True)),
    )
    try:
        async with session.begin_nested():
            await session.execute(
                counters.insert().from_select(
                    [
                        "id",
                        "tenant_id",
                        "sequence_id",
                        "year",
                        "next_value",
                        "created_at",
                        "updated_at",
                    ],
                    seed,
                )
            )
    except IntegrityError:
        pass  # a concurrent claimer created it first; its row is the one we increment


def _highest_issued(tenant_id: uuid.UUID, prefix: str, year: int | None) -> sa.ColumnElement[int]:
    """Scalar subquery for the largest counter value this tenant has already handed out under
    ``prefix``/``year``, or 0 when it has handed out none (an aggregate with no GROUP BY always
    yields exactly one row, so the enclosing INSERT ... SELECT always inserts exactly one).

    Read from the D-012 registry, not from any module's own table: every numbered document
    writes its number to ``core_documents.doc_number`` in the transaction that claims it, so
    core can see every issued number WITHOUT knowing which table a sequence numbers — and
    ``core_documents``' partial unique ``(tenant_id, doc_number)`` index is the very index a
    re-issued number collides on, so this reads exactly the set of strings a new counter could
    collide with. Numbers claimed by documents that stay OUT of the registry (HR's leave
    requests, timesheets and payroll runs carry plain number columns, not a registration) are
    invisible here and their counters still open at 1.

    Portable on both dialects (D-003): ``substr`` compares the fixed head rather than a LIKE
    pattern (no wildcard escaping, and every head ends in ``-`` so no head is a prefix of
    another), and the tail is CAST to INTEGER so a value that outgrew its padding still compares
    numerically. A NULL ``doc_number`` (a document registered but not yet numbered) fails the
    head comparison and drops out.

    **The tail must hold no further ``-``, or the CAST is not portable at all.** A head is only
    the whole number's shape when the sequence year-resets: a sequence with ``year_reset=False``
    (the default in industry-templates' NumberingFormatSpec) has head ``'PFX-'``, which is a
    prefix of every ``'PFX-2026-000001'`` a year-resetting sequence on the same prefix issued —
    and ``seed.py`` writes ``'STK-VOL-000001'`` shapes into the registry directly. Postgres
    raises on ``CAST('2026-000001' AS INTEGER)`` and 500s the counter-creation path; SQLite
    prefix-parses it to 2026 and silently opens the series at 2027, which is the worse half.
    Every number THIS head issued is head + digits, so excluding tails containing ``-`` keeps
    exactly the intended set and reads the same on both engines. ``-`` is not a LIKE wildcard,
    so this needs no ESCAPE clause on either dialect.
    """
    # Imported at CALL time, not module scope: core/models.py trailing-imports docflow and then
    # numbering to register both on Base.metadata, so a module-scope import here would make
    # ``import app.core.docflow`` (docflow first) fail on a partially-initialised module. By the
    # time a number is claimed both modules are fully loaded.
    from app.core.docflow import Document

    head = _number_head(prefix, year)
    documents = Document.__table__
    tail = sa.func.substr(documents.c.doc_number, len(head) + 1)
    return sa.func.coalesce(
        select(sa.func.max(sa.cast(tail, sa.Integer)))
        .where(
            documents.c.tenant_id == tenant_id,
            sa.func.substr(documents.c.doc_number, 1, len(head)) == head,
            tail.notlike("%-%"),
        )
        .scalar_subquery(),
        0,
    )
