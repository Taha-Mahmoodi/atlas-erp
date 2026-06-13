"""Stock-count WRITE engine (PLAN 5.4, D-038): create+populate / record-counted / post / cancel.

The read paths (``get_count``, ``list_counts``, ``list_count_lines``, ``variance_preview``) live in
``count_reads.py`` (split at the STRUCTURE §3 cap, writes-vs-reads from the start, the
stock_moves/stock_reads precedent); this module imports the reads it needs and the package
``__init__`` re-exports both halves as one surface.

A count captures the team's COUNTED quantity per (item, bin, lot) and posts the DIFFERENCE to live
on-hand as a stock ADJUSTMENT move — NEVER a bespoke journal (D-038): the adjustment runs the 5.3
costing engine + the price-difference journal via the event bus in the SAME transaction, so every
costing/GL/audit invariant is inherited. The whole post is one unit of work, so all variance moves'
journals + the count commit or roll back together (a closed-period count_date trips the period
trigger via the adjustment's journal and rolls the whole post back).

``post_count`` RE-READS live on-hand at post time as the authoritative system qty (NOT the stale
snapshot — D-038 concurrency safety), so a move landing between snapshot and post cannot post a
wrong variance: the resulting on-hand always equals the counted qty.
"""

from __future__ import annotations

import uuid
from datetime import UTC, date, datetime
from decimal import Decimal

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core import docflow
from app.core.exceptions import ConflictError, ValidationFailedError
from app.core.numbering import claim_number, ensure_sequence
from app.modules.inventory import queries
from app.modules.inventory.constants import (
    STOCK_COUNT_ADJUSTMENT_LINK,
    STOCK_COUNT_DOC_TYPE,
    STOCK_COUNT_NUMBER_PADDING,
    STOCK_COUNT_NUMBER_PREFIX,
    STOCK_COUNT_SEQUENCE_NAME,
    CountStatus,
    CountType,
    MoveType,
)
from app.modules.inventory.count_schemas import StockCountCreate
from app.modules.inventory.models import (
    Bin,
    StockCount,
    StockCountLine,
    StockQuant,
    Warehouse,
)
from app.modules.inventory.schemas import StockMoveCreate
from app.modules.inventory.service.count_reads import current_system_qty, get_count, get_line
from app.modules.inventory.service.stock_moves import create_move


async def _require_warehouse(
    session: AsyncSession, tenant_id: uuid.UUID, warehouse_id: uuid.UUID
) -> Warehouse:
    warehouse = await session.get(Warehouse, warehouse_id)
    if warehouse is None or warehouse.tenant_id != tenant_id:
        raise ValidationFailedError(
            message="The warehouse does not exist",
            code="inventory.warehouse_not_found",
            details={"warehouse_id": str(warehouse_id)},
        )
    return warehouse


async def _scope_quants(
    session: AsyncSession,
    tenant_id: uuid.UUID,
    warehouse_id: uuid.UUID,
    payload: StockCountCreate,
) -> list[StockQuant]:
    """The in-scope quants snapshotted into count lines. PHYSICAL = every quant in the warehouse;
    CYCLE = quants narrowed to the chosen ``item_ids`` and/or ``bin_ids`` (both optional). The quant
    join to inv_bins restricts to bins of THIS warehouse, so a count is always warehouse-bounded.
    One query — no per-quant N+1."""
    stmt = (
        select(StockQuant)
        .join(Bin, (Bin.tenant_id == StockQuant.tenant_id) & (Bin.id == StockQuant.bin_id))
        .where(StockQuant.tenant_id == tenant_id, Bin.warehouse_id == warehouse_id)
    )
    if CountType(payload.count_type) == CountType.CYCLE:
        if payload.item_ids:
            stmt = stmt.where(StockQuant.item_id.in_(payload.item_ids))
        if payload.bin_ids:
            stmt = stmt.where(StockQuant.bin_id.in_(payload.bin_ids))
    return list((await session.execute(stmt)).scalars().all())


async def create_count(
    session: AsyncSession, tenant_id: uuid.UUID, payload: StockCountCreate
) -> StockCount:
    """Create a count (DRAFT) and snapshot its lines from the current on-hand (PLAN 5.4, D-038).

    Claims the gapless CNT number + registers the document (D-012 claim-at-creation), then snapshots
    one line per in-scope quant with ``system_qty`` = current on-hand and ``counted_qty`` NULL. A
    PHYSICAL count enumerates every quant in the warehouse; a CYCLE count the chosen items/bins. The
    caller commits via uow; idempotency (D-013) is owned by the endpoint. Validates the warehouse
    exists. A warehouse with no stock yields a count with zero lines (the operator can still record
    counts by adding lines later — but v1 snapshots only existing quants; counting stock the system
    thinks is zero is a CYCLE count naming that item/bin, which appears as a line once a quant
    exists, or is handled by a direct positive ADJUSTMENT)."""
    warehouse = await _require_warehouse(session, tenant_id, payload.warehouse_id)
    count_date = payload.count_date or date.today()
    count_id = uuid.uuid4()
    document = await docflow.register_document(
        session,
        tenant_id,
        STOCK_COUNT_DOC_TYPE,
        count_id,
        doc_number=None,
        status=CountStatus.DRAFT.value,
    )
    await ensure_sequence(
        session,
        tenant_id,
        STOCK_COUNT_SEQUENCE_NAME,
        STOCK_COUNT_NUMBER_PREFIX,
        STOCK_COUNT_NUMBER_PADDING,
        year_reset=True,
    )
    count_number = await claim_number(
        session, tenant_id, STOCK_COUNT_SEQUENCE_NAME, on_date=count_date
    )
    count = StockCount(
        id=count_id,
        tenant_id=tenant_id,
        document_id=document.id,
        count_number=count_number,
        count_type=CountType(payload.count_type).value,
        warehouse_id=warehouse.id,
        status=CountStatus.DRAFT.value,
        count_date=count_date,
        description=payload.description,
    )
    session.add(count)
    await session.flush()
    await docflow.set_document_status(
        session, tenant_id, document.id, doc_number=count_number, status=CountStatus.DRAFT.value
    )
    await _populate_lines(session, tenant_id, count, payload)
    return count


async def _populate_lines(
    session: AsyncSession,
    tenant_id: uuid.UUID,
    count: StockCount,
    payload: StockCountCreate,
) -> None:
    """Snapshot one line per in-scope quant (PLAN 5.4): system_qty = current on-hand, counted_qty
    NULL. Lines are numbered 1..N in a stable (bin, item, lot) order so the count sheet reads
    predictably. One scope query; the line inserts are a single flush."""
    quants = await _scope_quants(session, tenant_id, count.warehouse_id, payload)
    quants.sort(key=lambda quant: (quant.bin_id.bytes, quant.item_id.bytes))
    for line_number, quant in enumerate(quants, start=1):
        session.add(
            StockCountLine(
                tenant_id=tenant_id,
                count_id=count.id,
                line_number=line_number,
                item_id=quant.item_id,
                bin_id=quant.bin_id,
                lot_id=quant.lot_id,
                system_qty=Decimal(quant.on_hand_qty),
            )
        )
    await session.flush()


async def record_counted(
    session: AsyncSession,
    tenant_id: uuid.UUID,
    count_id: uuid.UUID,
    line_id: uuid.UUID,
    counted_qty: Decimal,
) -> StockCountLine:
    """Record the counted quantity for one line and move the count to COUNTING (PLAN 5.4). Rejects a
    negative quantity (422) and a count that is already POSTED/CANCELLED (only DRAFT/COUNTING accept
    counts). Also re-snapshots ``system_qty`` to the line's CURRENT on-hand, so the preview baseline
    tracks reality between snapshot and recount (the post still re-validates against live
    on-hand)."""
    count = await get_count(session, tenant_id, count_id)
    _require_open(count)
    if counted_qty < 0:
        raise ValidationFailedError(
            message="Counted quantity cannot be negative",
            code="inventory.count_qty_negative",
            details={"counted_qty": str(counted_qty)},
        )
    line = await get_line(session, tenant_id, count_id, line_id)
    line.counted_qty = counted_qty
    line.system_qty = await current_system_qty(
        session, tenant_id, line.item_id, line.bin_id, line.lot_id
    )
    if CountStatus(count.status) == CountStatus.DRAFT:
        count.status = CountStatus.COUNTING.value
    await session.flush()
    return line


async def cancel_count(
    session: AsyncSession, tenant_id: uuid.UUID, count_id: uuid.UUID
) -> StockCount:
    """Cancel a count (PLAN 5.4): only DRAFT/COUNTING. A POSTED count is TERMINAL — its variances
    are real adjustment moves, so corrections are NEW counts/adjustments, never an un-post (the
    append-only ledger philosophy). Re-cancelling a CANCELLED count is a no-op-shaped conflict."""
    count = await get_count(session, tenant_id, count_id)
    if CountStatus(count.status) in (CountStatus.POSTED, CountStatus.CANCELLED):
        raise ConflictError(
            message="Only a draft or counting count can be cancelled",
            code="inventory.count_not_cancellable",
            details={"status": count.status},
        )
    count.status = CountStatus.CANCELLED.value
    await docflow.set_document_status(
        session, tenant_id, count.document_id, status=CountStatus.CANCELLED.value
    )
    await session.flush()
    return count


async def post_count(
    session: AsyncSession, tenant_id: uuid.UUID, count_id: uuid.UUID
) -> StockCount:
    """Post a count's variances as ADJUSTMENT moves (the heart, PLAN 5.4, D-038).

    For each line: RE-READ live on-hand (the authoritative system qty at post time — NOT the stale
    snapshot, D-038 concurrency safety), compute variance = counted − live-system; if zero, skip
    (adjustment_move_id stays NULL); else post ONE ADJUSTMENT move via stock_moves.create_move (a
    positive variance enters the bin at the item's current book cost; a negative variance leaves the
    bin and the engine computes its COGS-side value), link count.document → move.document via
    docflow ('counts'), and store variance_qty + adjustment_move_id + unit_cost on the line. EVERY
    line must
    be counted first (else 422). Idempotent (D-013): a POSTED count rejects re-post (no double
    adjustment). The caller runs this in run_in_uow, so every variance move's costing journal + the
    count commit as one transaction — a closed-period count_date rolls the whole post back."""
    count = await get_count(session, tenant_id, count_id)
    status = CountStatus(count.status)
    if status == CountStatus.POSTED:
        raise ConflictError(
            message="This count has already been posted",
            code="inventory.count_already_posted",
            details={"count_id": str(count_id)},
        )
    if status == CountStatus.CANCELLED:
        raise ConflictError(
            message="A cancelled count cannot be posted",
            code="inventory.count_cancelled",
            details={"count_id": str(count_id)},
        )
    lines = await _ordered_lines(session, tenant_id, count_id)
    _require_all_counted(lines)
    for line in lines:
        await _post_line(session, tenant_id, count, line)
    count.status = CountStatus.POSTED.value
    count.posted_at = datetime.now(UTC)
    await docflow.set_document_status(
        session, tenant_id, count.document_id, status=CountStatus.POSTED.value
    )
    await session.flush()
    return count


async def _post_line(
    session: AsyncSession,
    tenant_id: uuid.UUID,
    count: StockCount,
    line: StockCountLine,
) -> None:
    """Post ONE count line's variance (PLAN 5.4, D-038). Re-reads live on-hand, computes variance,
    and — when non-zero — posts the ADJUSTMENT move, links it to the count and records the result on
    the line. A zero variance leaves adjustment_move_id NULL (no move, no journal)."""
    live_system = await current_system_qty(
        session, tenant_id, line.item_id, line.bin_id, line.lot_id
    )
    counted = Decimal(line.counted_qty)  # _require_all_counted guarantees non-NULL
    variance = counted - live_system
    line.variance_qty = variance
    if variance == 0:
        return
    unit_cost = await queries.current_unit_cost(
        session, tenant_id, line.item_id, count.warehouse_id
    )
    # A positive variance enters the bin (to_bin) at the item's current book cost; a negative
    # variance leaves the bin (from_bin) and the costing engine computes the outbound value (the
    # passed unit_cost is ignored on the decrease side, per create_move's cost rule). The single
    # populated side carries the signed intent — quantity is always the positive magnitude.
    if variance > 0:
        move_payload = StockMoveCreate(
            move_type=MoveType.ADJUSTMENT,
            item_id=line.item_id,
            quantity=variance,
            to_bin_id=line.bin_id,
            lot_id=line.lot_id,
            move_date=count.count_date,
            reference=f"Count {count.count_number}",
            unit_cost=unit_cost,
        )
    else:
        move_payload = StockMoveCreate(
            move_type=MoveType.ADJUSTMENT,
            item_id=line.item_id,
            quantity=-variance,
            from_bin_id=line.bin_id,
            lot_id=line.lot_id,
            move_date=count.count_date,
            reference=f"Count {count.count_number}",
        )
    move = await create_move(session, tenant_id, move_payload)
    await docflow.link_documents(
        session,
        tenant_id,
        predecessor=count.document_id,
        successor=move.document_id,
        link_type=STOCK_COUNT_ADJUSTMENT_LINK,
    )
    line.adjustment_move_id = move.id
    # Record the cost actually used: the entry cost on a positive adjustment, the engine-computed
    # outbound cost on a negative one (written onto the move by the costing engine).
    line.unit_cost = Decimal(move.unit_cost) if move.unit_cost is not None else unit_cost


async def _ordered_lines(
    session: AsyncSession, tenant_id: uuid.UUID, count_id: uuid.UUID
) -> list[StockCountLine]:
    """Every line of a count in line-number order (the deterministic post order). One query."""
    return list(
        (
            await session.execute(
                select(StockCountLine)
                .where(
                    StockCountLine.tenant_id == tenant_id,
                    StockCountLine.count_id == count_id,
                )
                .order_by(StockCountLine.line_number.asc())
            )
        )
        .scalars()
        .all()
    )


def _require_open(count: StockCount) -> None:
    """A count accepts counted quantities only while DRAFT or COUNTING (PLAN 5.4)."""
    if CountStatus(count.status) not in (CountStatus.DRAFT, CountStatus.COUNTING):
        raise ConflictError(
            message="This count no longer accepts counted quantities",
            code="inventory.count_not_open",
            details={"status": count.status},
        )


def _require_all_counted(lines: list[StockCountLine]) -> None:
    """Every line must have a counted quantity before the count can post (PLAN 5.4) — an uncounted
    line means the count is unfinished, so posting it would silently assume zero. 422 with the
    offending line ids so the operator knows what to finish."""
    uncounted = [str(line.id) for line in lines if line.counted_qty is None]
    if uncounted:
        raise ValidationFailedError(
            message="Every line must be counted before the count can be posted",
            code="inventory.count_lines_uncounted",
            details={"uncounted_line_ids": uncounted},
        )


def variance_line_count(lines: list[StockCountLine]) -> int:
    """How many lines have a NON-ZERO variance against their snapshot (PLAN 5.4) — the router uses
    this against COUNT_POST_SYNC_MAX_VARIANCES to decide inline vs background post. It is an UPPER
    BOUND only (the post re-reads live on-hand, so the real variance set may differ); a conservative
    threshold based on the snapshot is enough to route large posts to the background job."""
    return sum(
        1
        for line in lines
        if line.counted_qty is not None and Decimal(line.counted_qty) != Decimal(line.system_qty)
    )


async def count_variance_estimate(
    session: AsyncSession, tenant_id: uuid.UUID, count_id: uuid.UUID
) -> int:
    """The snapshot-based non-zero-variance line count for a count (PLAN 5.4) — the cheap routing
    input the endpoint reads before choosing inline vs background post. One query for the lines."""
    await get_count(session, tenant_id, count_id)
    lines = await _ordered_lines(session, tenant_id, count_id)
    return variance_line_count(lines)


__all__ = [
    "cancel_count",
    "count_variance_estimate",
    "create_count",
    "post_count",
    "record_counted",
    "variance_line_count",
]
