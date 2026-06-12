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
from datetime import date

import sqlalchemy as sa
from sqlalchemy import select
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
    """Per-tenant gapless counter for one document kind (D-012).

    ``name`` is the namespaced sequence key (e.g. ``'finance.invoice'``); a claim formats
    ``{prefix}-{year?}-{padded next_value}`` (e.g. ``INV-2026-00001``). When ``year_reset``
    is set the running number restarts at 1 each calendar year and the year segment is
    rendered; ``current_year`` records which year the counter currently belongs to so the
    first claim of a new year resets it on demand (no rollover job, per D-012). Not
    AuditMixin: sequence rows are infrastructure counters mutated on every claim, not
    business state — auditing every increment would be noise (documented exclusion)."""

    __tablename__ = "core_number_sequences"
    __table_args__ = (
        # One sequence per (tenant, name). Explicit name: the D-022 convention keys on
        # column 0 (tenant_id) only and would collide with tenant_unique() below.
        sa.UniqueConstraint("tenant_id", "name", name="uq_core_number_sequences_tenant_id_name"),
        # UNIQUE(tenant_id, id) so other tenant-scoped tables could reference a sequence via
        # the composite-FK backstop if ever needed (D-007 item 4).
        sa.UniqueConstraint("tenant_id", "id", name="uq_core_number_sequences_tenant_id"),
        tenant_fk("adm_tenants"),
    )

    name: Mapped[str] = mapped_column(sa.String(100), nullable=False)
    prefix: Mapped[str] = mapped_column(sa.String(20), nullable=False)
    padding: Mapped[int] = mapped_column(sa.Integer, nullable=False)
    # Next number to hand out. The atomic claim does next_value = next_value + 1 RETURNING
    # the post-increment value, so the FIRST claim of a sequence at next_value=1 returns 1.
    next_value: Mapped[int] = mapped_column(
        sa.Integer, nullable=False, default=1, server_default=sa.text("1")
    )
    year_reset: Mapped[bool] = mapped_column(
        sa.Boolean, nullable=False, default=False, server_default=sa.false()
    )
    # The year the running counter belongs to (NULL when year_reset is off).
    current_year: Mapped[int | None] = mapped_column(sa.Integer, nullable=True)


def _format_number(prefix: str, padding: int, value: int, year: int | None) -> str:
    """Render ``{prefix}-{year?}-{padded value}`` — the year segment is present only when
    the sequence year-resets (D-012). e.g. ('INV', 5, 1, 2026) -> 'INV-2026-00001'."""
    padded = str(value).zfill(padding)
    if year is None:
        return f"{prefix}-{padded}"
    return f"{prefix}-{year}-{padded}"


async def ensure_sequence(
    session: AsyncSession,
    tenant_id: uuid.UUID,
    name: str,
    prefix: str,
    padding: int,
    year_reset: bool,
) -> NumberSequence:
    """Idempotent creator for provisioning/seed (D-012: year rollover and sequence setup
    need no job — the row is created on demand). Returns the existing row unchanged if the
    (tenant, name) sequence already exists, otherwise inserts it at next_value=1.

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

    current_year = date.today().year if year_reset else None
    await session.execute(
        sa.insert(NumberSequence.__table__).values(
            id=uuid.uuid4(),
            tenant_id=tenant_id,
            name=name,
            prefix=prefix,
            padding=padding,
            next_value=1,
            year_reset=year_reset,
            current_year=current_year,
        )
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
    ``UPDATE core_number_sequences SET next_value = next_value + 1
      WHERE tenant_id=:t AND name=:n RETURNING next_value`` — the RETURNING value is the
    post-increment counter; the row lock the UPDATE takes serializes concurrent claimers so
    two claims can never read the same number (verified on aiosqlite >= 3.35 and Postgres).

    Year reset (when ``year_reset``): if ``on_date.year`` differs from the stored
    ``current_year``, the counter is reset to 1 for the new year FIRST (a guarded UPDATE
    that only fires while current_year is still the old value, so a concurrent claimer that
    reset it already cannot double-reset), then the normal atomic increment claims 1.

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

    table = NumberSequence.__table__
    claim_year: int | None = None
    if sequence.year_reset:
        claim_year = on_date.year
        if sequence.current_year != claim_year:
            # Reset to 1 for the new year, guarded on the OLD current_year so a racing
            # claimer that already rolled the year over does not reset a second time.
            await session.execute(
                sa.update(table)
                .where(
                    table.c.tenant_id == tenant_id,
                    table.c.name == sequence_name,
                    table.c.current_year.is_not_distinct_from(sequence.current_year),
                )
                .values(next_value=1, current_year=claim_year)
            )

    result = await session.execute(
        sa.update(table)
        .where(table.c.tenant_id == tenant_id, table.c.name == sequence_name)
        .values(next_value=table.c.next_value + 1)
        .returning(table.c.next_value)
    )
    next_after = result.scalar_one()
    claimed_value = next_after - 1

    # The Core UPDATE changed the row out from under the loaded ORM object; expire it so its
    # attributes reload from the DB on next access rather than being marked dirty (which
    # would trigger a redundant ORM UPDATE on the next flush).
    formatted = _format_number(sequence.prefix, sequence.padding, claimed_value, claim_year)
    session.expire(sequence)
    return formatted
