"""Industry module (PLAN 14 / D-060) — the INDUSTRY CONFIGURATION LAYER, Atlas's answer to SAP
industry solutions and the product's headline differentiator.

PLAN 14.1 ships the YAML industry-template schema (``industry-templates/_schema.yaml``), a
validating idempotent loader, and five meaningfully-different shipped templates (manufacturing,
retail, professional-services, healthcare, construction). A tenant picks one at onboarding (14.2)
and the loader instantiates its whole configuration — COA preset, tax codes, currencies, UoMs,
item categories, typed custom fields (D-016), approval presets, module toggles, terminology
overrides and numbering formats — in ONE transaction.

§5-clean ownership (D-060): the loader applies the CORE/ADMIN-owned slices directly (custom-field
defs via core/custom_fields, numbering sequences via core/numbering, terminology + module-toggle
TenantSettings via admin) and PUBLISHES ``IndustryTemplateApplying`` for the cross-module slices —
finance (COA + tax codes + currencies), inventory (UoMs + item categories) and procurement
(approval presets) each create THEIR slice idempotently in their handlers.py. The industry module
NEVER imports those modules' services.

Importing this package registers the module's permission keys in the core RBAC catalog
(constants.py runs ``register_permissions`` at import), the same way every other module does.
"""

from app.modules.industry import (
    constants as _constants,  # noqa: F401 - import-time perm registration
)
