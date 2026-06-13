"""Configurable tax codes (PLAN 4.4), the fourth file in the finance ``models/`` package.

A ``TaxCode`` (``fin_tax_codes``) is the line-level tax configuration AP/AR and Sales apply to a
document line: a rate, whether the line price already includes that tax, and the two GL accounts
the calculated tax posts to (one for OUTPUT/sales tax payable, one for INPUT/purchase tax
recoverable). The calculation math (inclusive vs exclusive, rounding, document grouping) lives in
``service/tax.py``; this file is only the persisted configuration.

``rate_percent`` is a ``MoneyType`` column (D-015 exact decimal, scale 6) holding a PERCENTAGE,
not a money amount — e.g. ``Decimal("20")`` means 20%, ``Decimal("19.6")`` means 19.6%. A
percentage is an exact decimal like money, so the same exact-on-both-engines TypeDecorator applies;
the column name and this docstring carry the "it is a percent" meaning. The fraction the calc
service multiplies by is ``rate_percent / 100``.

Both account links are NULLABLE composite tenant FKs to ``fin_accounts`` (D-007 backstop): a tax
code may wire only the side it is used for (a pure output VAT code needs only the payable account).
The calc service resolves the right account by ``TaxDirection`` and raises a clear 422 when the
needed side is unwired, rather than guessing. UNIQUE(tenant_id, code) keys the code per tenant.

Enum-valued behaviour is captured by plain booleans here (``is_inclusive``, ``is_active``),
matching how the rest of finance stores configuration; ``jurisdiction`` is a free ISO-style string
(e.g. ``'GB'``) for grouping/reporting, not a constrained enum. Audited (D-010): a tax code's rate
or wiring changes where money lands, so edits are tracked.
"""

import uuid

import sqlalchemy as sa
from sqlalchemy.orm import Mapped, mapped_column

from app.core.models import (
    AuditMixin,
    Base,
    TenantMixin,
    TimestampMixin,
    UuidPKMixin,
    tenant_fk,
    tenant_unique,
)
from app.core.money import MoneyType


class TaxCode(UuidPKMixin, TenantMixin, AuditMixin, TimestampMixin, Base):
    """One configurable tax code (PLAN 4.4). ``code`` is the short key a line references
    (e.g. ``'VAT20'``); ``rate_percent`` is the percentage (20 means 20%), stored exactly via
    MoneyType (D-015). ``is_inclusive`` says whether a line's base amount already contains the tax
    (gross) or has it added on top (net). ``tax_payable_account_id`` collects OUTPUT (sales) tax —
    a liability owed to the authority; ``tax_receivable_account_id`` collects INPUT (purchase) tax —
    recoverable from the authority. Both are optional so a code wires only the side it serves."""

    __tablename__ = "fin_tax_codes"
    __table_args__ = (
        sa.UniqueConstraint("tenant_id", "code", name="uq_fin_tax_codes_tenant_id_code"),
        tenant_unique(),
        tenant_fk("adm_tenants"),
        # Composite tenant FKs: a tax code's posting accounts must belong to the same tenant.
        tenant_fk("fin_accounts", "tax_payable_account_id"),
        tenant_fk("fin_accounts", "tax_receivable_account_id"),
    )

    code: Mapped[str] = mapped_column(sa.String(40), nullable=False)
    name: Mapped[str] = mapped_column(sa.String(200), nullable=False)
    # A PERCENTAGE (20 == 20%), exact decimal via MoneyType (D-015) — NOT a money amount.
    rate_percent: Mapped[object] = mapped_column(MoneyType(), nullable=False)
    jurisdiction: Mapped[str | None] = mapped_column(sa.String(20), nullable=True)
    is_inclusive: Mapped[bool] = mapped_column(
        sa.Boolean, nullable=False, default=False, server_default=sa.false()
    )
    is_active: Mapped[bool] = mapped_column(
        sa.Boolean, nullable=False, default=True, server_default=sa.true()
    )
    # OUTPUT tax (sales) payable account; INPUT tax (purchase) receivable account. Nullable: a
    # code may wire only the side it is used on. The calc service resolves by TaxDirection.
    tax_payable_account_id: Mapped[uuid.UUID | None] = mapped_column(sa.Uuid, nullable=True)
    tax_receivable_account_id: Mapped[uuid.UUID | None] = mapped_column(sa.Uuid, nullable=True)
