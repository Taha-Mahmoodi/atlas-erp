"""Approval rules (PLAN 6.2): the ``ApprovalRule`` value-threshold entity (D-040).

The DATA-DRIVEN release rule: a requisition / PO whose total is AT OR ABOVE the active threshold for
its document_type requires approval before it can advance (submit → stays SUBMITTED / send → goes
PENDING_APPROVAL); below the threshold it auto-approves. This is a single-characteristic (amount)
rule per the s4hana-parity Procurement section — multi-characteristic / multi-step release
strategies
are the documented later.

ONE active rule per (tenant, document_type) is the v1 model: ``UNIQUE(tenant_id, document_type)`` so
the evaluation is an indexed point lookup with no ambiguity (a future version with overlapping
characteristic-scoped rules would relax this). NOT DocumentMixin: a rule is configuration, not a
posted document — it carries no gapless number and registers no flow node.
"""

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
from app.modules.procurement.constants import ApprovalDocumentType


class ApprovalRule(UuidPKMixin, TenantMixin, AuditMixin, TimestampMixin, Base):
    """A value-threshold approval rule (PLAN 6.2, D-040). ``document_type`` is REQUISITION or
    PURCHASE_ORDER (which document the rule governs). ``threshold_amount`` is the at-or-above value
    that requires approval; ``currency_code`` is the rule's currency. ``is_active`` toggles the rule
    without deleting it (an inactive rule is ignored by the evaluator — no active rule ⇒ no approval
    needed). UNIQUE(tenant_id, document_type) so there is exactly one rule slot per document type.
    Audited (D-010): a rule defines who-must-approve-what, a security-relevant control."""

    __tablename__ = "proc_approval_rules"
    __table_args__ = (
        sa.UniqueConstraint(
            "tenant_id", "document_type", name="uq_proc_approval_rules_tenant_id_document_type"
        ),
        tenant_unique(),
        tenant_fk("adm_tenants"),
        # Bare token: the D-022 ck convention wraps it as ck_<table>_<name> ->
        # ck_proc_approval_rules_threshold_non_negative (the vendor payment-terms CHECK precedent).
        sa.CheckConstraint("threshold_amount >= 0", name="threshold_non_negative"),
    )

    document_type: Mapped[str] = mapped_column(
        sa.String(20), nullable=False, default=ApprovalDocumentType.PURCHASE_ORDER.value
    )
    threshold_amount: Mapped[object] = mapped_column(MoneyType(), nullable=False)
    currency_code: Mapped[str] = mapped_column(sa.String(3), nullable=False)
    is_active: Mapped[bool] = mapped_column(
        sa.Boolean, nullable=False, default=True, server_default=sa.true()
    )
    description: Mapped[str | None] = mapped_column(sa.String(500), nullable=True)
