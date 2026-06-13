"""The tax engine (PLAN 4.4): configurable tax codes + the calculation AP/AR/Sales call.

Two concerns live here, both owned by the service layer (CLAUDE.md rule 7):

1. **Calculation** (pure, no DB): ``calculate_line_tax`` turns one line's base amount + a tax code +
   a direction into a ``TaxCalculation`` (net / tax / gross + the account to post to), and
   ``calculate_document_tax`` groups many lines by tax code into the tax journal lines a document
   posts. The math is exact-decimal (D-015): every amount quantizes ROUND_HALF_UP to the currency's
   minor unit, and document-level grouping uses ``allocate`` so per-code tax sums reconstitute
   exactly with no stray rounding cent.

2. **CRUD** (DB): create / update / list / get tax codes, validating that any wired posting account
   exists in the tenant. The DB UNIQUE(tenant_id, code) backstops the duplicate-code check.

Inclusive vs exclusive (the SAP-style distinction):
- EXCLUSIVE: the line's base amount IS the net; tax is added on top. ``tax = net * rate``,
  ``gross = net + tax``.
- INCLUSIVE: the line's base amount IS the gross (tax already inside the price). ``net = gross /
  (1 + rate)``, ``tax = gross - net``. Deriving tax as ``gross - net`` (rather than ``gross * rate /
  (1+rate)`` directly) keeps net + tax == gross EXACTLY after quantization — the two rounded parts
  always reconstitute the rounded gross.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass
from decimal import Decimal

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.exceptions import ConflictError, NotFoundError, ValidationFailedError
from app.core.money import allocate, currency_decimals, quantize_money
from app.modules.finance.constants import TaxDirection
from app.modules.finance.models import Account, TaxCode
from app.modules.finance.schemas import TaxCodeCreate, TaxCodeUpdate

_HUNDRED = Decimal(100)


@dataclass(frozen=True)
class TaxCalculation:
    """The result of taxing one line (PLAN 4.4). ``net`` is the pre-tax base, ``tax`` the tax
    amount, ``gross`` = net + tax (all quantized to the currency's minor unit, D-015).
    ``tax_account_id`` is the GL account the ``tax`` posts to — the tax code's payable account for
    OUTPUT (sales) tax, its receivable account for INPUT (purchase) tax. ``tax_code`` and
    ``direction`` are carried so a document-level caller groups/routes without re-deriving them."""

    tax_code: str
    direction: TaxDirection
    net_amount: Decimal
    tax_amount: Decimal
    gross_amount: Decimal
    tax_account_id: uuid.UUID | None


@dataclass(frozen=True)
class TaxLine:
    """One tax journal line a document must post (PLAN 4.4): the summed tax for a single tax code,
    the account it posts to, and the total net it was levied on. ``line_tax`` is the same tax
    split back across the group's lines (largest-remainder ``allocate``) so a caller that wants
    per-line tax detail has figures that sum EXACTLY to ``tax_amount`` — no drift."""

    tax_code: str
    direction: TaxDirection
    tax_account_id: uuid.UUID | None
    taxable_net: Decimal
    tax_amount: Decimal
    line_tax: list[Decimal]


@dataclass(frozen=True)
class DocumentTaxSummary:
    """The document-level result (PLAN 4.4): the per-code tax lines AP/AR build the journal from,
    plus the rolled-up net / tax / gross totals. ``tax_lines`` is one entry per tax code so a
    document posts exactly one tax line per code; AP/AR pair these with the net-to-expense/revenue
    and gross-to-AP/AR-control lines to form a balanced entry."""

    net_total: Decimal
    tax_total: Decimal
    gross_total: Decimal
    tax_lines: list[TaxLine]


def _rate_fraction(tax_code: TaxCode) -> Decimal:
    """The tax code's rate as a fraction (20% -> Decimal('0.20')). Kept full-precision; the
    quantization happens on the resulting money amount, never on the rate."""
    return Decimal(str(tax_code.rate_percent)) / _HUNDRED


def _account_for(tax_code: TaxCode, direction: TaxDirection) -> uuid.UUID | None:
    """The GL account this tax posts to for ``direction``: the payable account for OUTPUT (sales)
    tax, the receivable account for INPUT (purchase) tax."""
    if direction is TaxDirection.OUTPUT:
        return tax_code.tax_payable_account_id
    return tax_code.tax_receivable_account_id


def calculate_line_tax(
    base_amount: Decimal,
    tax_code: TaxCode,
    *,
    direction: TaxDirection,
    currency_code: str = "USD",
) -> TaxCalculation:
    """Tax one line (PLAN 4.4). ``base_amount`` is the gross when ``tax_code.is_inclusive`` else the
    net. All three outputs quantize HALF_UP to ``currency_code``'s minor unit (D-015); for inclusive
    tax, ``tax`` is derived as ``gross - net`` so net + tax == gross exactly after rounding."""
    places = currency_decimals(currency_code)
    rate = _rate_fraction(tax_code)
    if tax_code.is_inclusive:
        gross = quantize_money(base_amount, places)
        net = quantize_money(base_amount / (Decimal(1) + rate), places)
        tax = gross - net
    else:
        net = quantize_money(base_amount, places)
        tax = quantize_money(net * rate, places)
        gross = net + tax
    return TaxCalculation(
        tax_code=tax_code.code,
        direction=direction,
        net_amount=net,
        tax_amount=tax,
        gross_amount=gross,
        tax_account_id=_account_for(tax_code, direction),
    )


def calculate_document_tax(
    lines: list[tuple[Decimal, TaxCode, TaxDirection]],
    *,
    currency_code: str = "USD",
) -> DocumentTaxSummary:
    """Tax a whole document and group the tax per code (PLAN 4.4).

    Each ``(base_amount, tax_code, direction)`` line is taxed via ``calculate_line_tax``; lines are
    then grouped by ``(code, direction)`` into ONE tax line per group. The grouped tax is NOT the
    sum of the per-line rounded tax (which can drift a cent) — it is the group's net total taxed
    ONCE, then ``allocate``d back across the group's line nets so each line carries a tax share that
    sums EXACTLY to the posted group tax (D-015 largest-remainder). Returns enough for AP/AR to
    build the journal: net per line feeds expense/revenue, each TaxLine posts to its tax account,
    and gross feeds the AP/AR control."""
    places = currency_decimals(currency_code)
    # Per-group running totals, keyed by (code, direction); insertion order preserved for stable
    # output. Each group tracks its taxable net, the rate code object, and the resolved account.
    groups: dict[tuple[str, TaxDirection], dict[str, object]] = {}
    net_total = Decimal(0)
    for base_amount, tax_code, direction in lines:
        calc = calculate_line_tax(
            base_amount, tax_code, direction=direction, currency_code=currency_code
        )
        net_total += calc.net_amount
        key = (tax_code.code, direction)
        group = groups.get(key)
        if group is None:
            groups[key] = {
                "code": tax_code,
                "direction": direction,
                "account_id": calc.tax_account_id,
                "net": calc.net_amount,
                "line_nets": [calc.net_amount],
            }
        else:
            group["net"] = group["net"] + calc.net_amount  # type: ignore[operator]
            group["line_nets"].append(calc.net_amount)  # type: ignore[attr-defined]

    tax_lines: list[TaxLine] = []
    tax_total = Decimal(0)
    for (code, direction), group in groups.items():
        tax_code = group["code"]  # type: ignore[assignment]
        taxable_net: Decimal = group["net"]  # type: ignore[assignment]
        line_nets: list[Decimal] = group["line_nets"]  # type: ignore[assignment]
        # Tax the group's net ONCE so the code's posted tax is exact (no per-line rounding drift).
        rate = _rate_fraction(tax_code)
        if tax_code.is_inclusive:
            # The group net is the sum of the per-line derived nets; gross it up ONCE so the
            # posted group tax (gross - net) ties net + tax == gross at the group level.
            group_gross = quantize_money(taxable_net * (Decimal(1) + rate), places)
            group_tax = group_gross - taxable_net
        else:
            group_tax = quantize_money(taxable_net * rate, places)
        # Split the once-rounded group tax back across the line nets so a per-line tax detail
        # (line_tax) sums EXACTLY to group_tax — largest-remainder, no drift (D-015). A zero
        # group tax allocates to all-zero shares.
        line_tax = allocate(group_tax, line_nets, places)
        tax_total += group_tax
        tax_lines.append(
            TaxLine(
                tax_code=code,
                direction=direction,
                tax_account_id=group["account_id"],  # type: ignore[arg-type]
                taxable_net=taxable_net,
                tax_amount=group_tax,
                line_tax=line_tax,
            )
        )

    return DocumentTaxSummary(
        net_total=net_total,
        tax_total=tax_total,
        gross_total=net_total + tax_total,
        tax_lines=tax_lines,
    )


# --- CRUD ---------------------------------------------------------------------


async def _tax_code_by_code(
    session: AsyncSession, tenant_id: uuid.UUID, code: str
) -> TaxCode | None:
    stmt = select(TaxCode).where(TaxCode.tenant_id == tenant_id, TaxCode.code == code)
    return (await session.execute(stmt)).scalar_one_or_none()


async def _require_account(
    session: AsyncSession, tenant_id: uuid.UUID, account_id: uuid.UUID
) -> None:
    """Validate a wired posting account exists in the tenant (PLAN 4.4) — fail loud at config time
    rather than at the first posting. Mirrors posting_defaults' account check."""
    account = (
        await session.execute(
            select(Account.id).where(Account.tenant_id == tenant_id, Account.id == account_id)
        )
    ).scalar_one_or_none()
    if account is None:
        raise ValidationFailedError(
            message="The tax account does not exist in this tenant",
            code="finance.tax_account_not_found",
            details={"account_id": str(account_id)},
        )


async def get_tax_code(
    session: AsyncSession, tenant_id: uuid.UUID, tax_code_id: uuid.UUID
) -> TaxCode:
    tax_code = await session.get(TaxCode, tax_code_id)
    if tax_code is None or tax_code.tenant_id != tenant_id:
        raise NotFoundError(message="Tax code not found", code="finance.tax_code_not_found")
    return tax_code


async def create_tax_code(
    session: AsyncSession, tenant_id: uuid.UUID, payload: TaxCodeCreate
) -> TaxCode:
    """Create a tax code (PLAN 4.4). Rejects a duplicate code (DB UNIQUE backstops) and validates
    any wired payable/receivable account exists in the tenant."""
    if await _tax_code_by_code(session, tenant_id, payload.code) is not None:
        raise ConflictError(
            message=f"A tax code with code {payload.code} already exists",
            code="finance.tax_code_conflict",
            details={"code": payload.code},
        )
    for account_id in (payload.tax_payable_account_id, payload.tax_receivable_account_id):
        if account_id is not None:
            await _require_account(session, tenant_id, account_id)
    tax_code = TaxCode(
        tenant_id=tenant_id,
        code=payload.code,
        name=payload.name,
        rate_percent=payload.rate_percent,
        jurisdiction=payload.jurisdiction,
        is_inclusive=payload.is_inclusive,
        is_active=payload.is_active,
        tax_payable_account_id=payload.tax_payable_account_id,
        tax_receivable_account_id=payload.tax_receivable_account_id,
    )
    session.add(tax_code)
    await session.flush()
    return tax_code


async def update_tax_code(
    session: AsyncSession,
    tenant_id: uuid.UUID,
    tax_code_id: uuid.UUID,
    payload: TaxCodeUpdate,
) -> TaxCode:
    """Partial update of a tax code's mutable fields (D-010: mutate the loaded object so the audit
    diff is captured). ``code`` is immutable (a posted line references it) and absent from the
    schema; wired accounts are re-validated when set."""
    tax_code = await get_tax_code(session, tenant_id, tax_code_id)
    data = payload.model_dump(exclude_unset=True)
    for field in ("tax_payable_account_id", "tax_receivable_account_id"):
        if data.get(field) is not None:
            await _require_account(session, tenant_id, data[field])
    for field, value in data.items():
        setattr(tax_code, field, value)
    await session.flush()
    return tax_code


async def list_tax_codes(
    session: AsyncSession,
    tenant_id: uuid.UUID,
    *,
    cursor: str | None,
    limit: int,
    is_active: bool | None = None,
) -> object:
    """Keyset-paginated tax-code list ordered by code (D-014). ``is_active`` narrows the set and
    folds into the cursor fingerprint so a cursor cannot cross filtered views. Returns a ``Page``
    of ORM objects; the router re-validates into ``TaxCodeRead`` (imported lazily to keep the
    pagination/schema dependency out of this module's import-time surface)."""
    from app.core.pagination import OrderKey, SortDirection, filter_fingerprint, paginate

    stmt = select(TaxCode).where(TaxCode.tenant_id == tenant_id)
    if is_active is not None:
        stmt = stmt.where(TaxCode.is_active == is_active)
    return await paginate(
        session,
        stmt,
        order_by=[OrderKey(TaxCode.code, SortDirection.ASC)],
        pk=TaxCode.id,
        cursor=cursor,
        limit=limit,
        filters=filter_fingerprint(is_active),
    )
