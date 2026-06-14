"""Industry domain events (D-011/D-060) — the cross-module provisioning seam.

``IndustryTemplateApplying`` is PUBLISHED by the industry loader (in ``run_in_uow`` under
``system_context``) once it has parsed + validated a template and applied its CORE/ADMIN-owned
slices (custom-field defs, numbering sequences, terminology + module-toggle TenantSettings). Each
OWNING module subscribes a provisioning handler in its ``handlers.py`` and creates ITS slice
IDEMPOTENTLY in the SAME transaction (D-011 drains before commit):

    finance/handlers   -> account groups + accounts (COA preset), tax codes, currencies
    inventory/handlers -> UoMs + item categories
    procurement/handlers -> the value-threshold approval presets

This keeps the industry module §5-clean: it NEVER imports finance/inventory/procurement services.
It carries the WHOLE validated template (a frozen Pydantic ``IndustryTemplate``) so each handler
reads only its own slice off the typed payload — a plain-data event with no behaviour (D-011).
"""

from typing import ClassVar

from app.core.events import DomainEvent
from app.modules.industry.constants import INDUSTRY_TEMPLATE_APPLYING_EVENT_KEY
from app.modules.industry.schemas import IndustryTemplate


class IndustryTemplateApplying(DomainEvent):
    """Published when an industry template is being applied to a tenant (D-060). Carries the
    validated, normalized template so each owning module's provisioning handler creates its slice
    idempotently in the same transaction. ``tenant_id`` (from DomainEvent) is the target tenant;
    provisioning runs under ``system_context`` so the handlers stamp tenant_id explicitly."""

    key: ClassVar[str] = INDUSTRY_TEMPLATE_APPLYING_EVENT_KEY

    template: IndustryTemplate
