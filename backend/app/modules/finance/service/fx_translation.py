"""Posting-time FX translation of journal lines (D-019), extracted from service/journal.py.

Translation happens EXACTLY ONCE, at posting (D-019): when an entry's currency differs from the
tenant's functional currency, each line's functional debit/credit is recomputed as
``quantize(transaction_amount × rate, functional_decimals)`` HALF_UP. Quantizing each line
independently can leave the functional debit total off the functional credit total by a cent —
the balance trigger SUM-checks the FUNCTIONAL amounts, so that residual must be absorbed, NOT
posted as a separate rounding line (a functional-only line has zero transaction amounts and would
violate the mandated one-side CHECK, D-017). So the residual cent is folded into the LARGEST line
on the short side via ``core/money.allocate`` (largest-remainder), making functional debits ==
credits EXACTLY with no special lines.

When the entry currency EQUALS the functional currency, functional == transaction (unchanged):
the caller skips this module entirely.
"""

from __future__ import annotations

import uuid
from decimal import Decimal

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.money import allocate, currency_decimals
from app.modules.finance.constants import RateKind
from app.modules.finance.models import JournalEntry, JournalLine
from app.modules.finance.service import fx


async def translate_entry_lines(
    session: AsyncSession,
    tenant_id: uuid.UUID,
    entry: JournalEntry,
    lines: list[JournalLine],
    rate_override: Decimal | None,
) -> None:
    """Posting-time FX translation of an entry's lines (D-019), called by the posting protocol.

    When the entry currency EQUALS the functional currency, functional == transaction (already set
    at draft creation) — nothing to do. Otherwise resolve the SPOT rate for posting_date (or use
    the caller-supplied ``rate_override``) and recompute each line's functional amounts via
    ``apply_translation``, which balances the functional residual into the largest line. Translation
    happens exactly once, here; posted lines are never re-translated (immutability triggers).

    A REVERSAL (reverses_entry_id set) carries the ORIGINAL's frozen functional amounts swapped —
    re-translating it would re-rate at a different date and break clearing-time realized math, so
    reversals are never re-translated (D-019).

    A tenant with NO functional currency configured is the v1 single-currency default: functional
    already equals transaction, so translation is a no-op — multi-currency is opt-in by configuring
    a functional currency + rates.
    """
    if entry.reverses_entry_id is not None:
        return
    func_code = await fx.functional_currency_or_none(session, tenant_id)
    if func_code is None or entry.currency_code == func_code:
        return
    rate = (
        rate_override
        if rate_override is not None
        else await fx.get_rate(
            session,
            tenant_id,
            entry.currency_code,
            func_code,
            entry.posting_date,
            RateKind.SPOT,
        )
    )
    apply_translation(lines, rate, currency_decimals(func_code))


def apply_translation(
    lines: list[JournalLine], rate: Decimal, functional_decimals: int
) -> None:
    """Translate every line's functional amounts at ``rate`` and BALANCE the functional residual.

    Mutates the loaded ``lines`` in place (loaded-object mutation so audit captures the change and
    the audit bulk-write assertion holds, D-010). Steps:

    1. Per line, functional side = quantize(transaction side × rate, functional_decimals); the
       other functional side stays 0 (one-sided lines, D-017).
    2. The per-line quantization can make Σ functional_debit differ from Σ functional_credit. Both
       sides translate the SAME total transaction amount at the SAME rate, so their UNQUANTIZED
       functional totals are equal; the post-quantization gap is at most a few minor units. Snap
       each side's per-line amounts to its own exact total via largest-remainder ``allocate`` so
       each side sums to the SAME quantized grand total — i.e. Σ debit == Σ credit exactly. The
       residual cent lands on the largest line(s), never a separate line.
    """
    quantum = Decimal(1).scaleb(-functional_decimals)

    # The exact (unquantized) functional total each side translates to — equal by construction
    # (both sides are the same balanced transaction total × the same rate). Quantize that shared
    # total ONCE; both sides must sum to it.
    transaction_debit_total = sum(
        (line.transaction_debit_amount for line in lines), Decimal(0)
    )
    functional_total = (transaction_debit_total * rate).quantize(quantum)

    _balance_side(lines, "debit", rate, functional_total, quantum)
    _balance_side(lines, "credit", rate, functional_total, quantum)


def _balance_side(
    lines: list[JournalLine],
    side: str,
    rate: Decimal,
    functional_total: Decimal,
    quantum: Decimal,
) -> None:
    """Set the ``side`` (debit|credit) functional amounts so they sum EXACTLY to
    ``functional_total``. Lines with a zero transaction amount on this side get 0 (they are the
    other side); the non-zero lines split ``functional_total`` by their transaction weight via
    largest-remainder ``allocate``, so the parts always reconstitute the total and the residual
    cent lands on the largest line."""
    transaction_attr = f"transaction_{side}_amount"
    functional_attr = f"functional_{side}_amount"

    indices = [i for i, line in enumerate(lines) if getattr(line, transaction_attr) > 0]
    if not indices:
        # No line carries this side: every functional amount on this side is 0.
        for line in lines:
            setattr(line, functional_attr, Decimal(0))
        return

    weights = [getattr(lines[i], transaction_attr) for i in indices]
    places = -quantum.as_tuple().exponent
    parts = allocate(functional_total, weights, places=places)

    part_by_index = dict(zip(indices, parts, strict=True))
    for i, line in enumerate(lines):
        setattr(line, functional_attr, part_by_index.get(i, Decimal(0)))
