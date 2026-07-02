"""Industry module constants (STRUCTURE §3): the shipped template names, the provisioning
event key, the terminology TenantSetting key prefix, the module-toggle TenantSetting key, and
the permission keys (registered into the core RBAC catalog at import, D-009).

The industry layer (PLAN 14.1 / D-060) is the configuration layer: a tenant picks one of the five
SHIPPED_TEMPLATES at onboarding and the loader applies it idempotently. The templates live as YAML
files in the top-level ``industry-templates/`` dir (STRUCTURE §1), NOT in code — this file only
names them and the loader reads/validates the files against ``industry-templates/_schema.yaml``.
"""

from app.core.rbac import register_permissions

# The five shipped template names (PLAN 14.1). Each is a ``{name}.yaml`` file in the top-level
# industry-templates/ dir whose ``name`` field equals this stem; the loader rejects any other name.
SHIPPED_TEMPLATES: tuple[str, ...] = (
    "manufacturing",
    "retail",
    "professional-services",
    "healthcare",
    "construction",
)

# The domain-event key the loader publishes once it has parsed + validated a template and applied
# its core/admin-owned slices (D-060). Each OWNING module (finance, inventory, procurement) handles
# its slice in the SAME transaction (D-011 run_in_uow) — the §5-clean cross-module provisioning seam
# (the industry module never imports finance/inventory/procurement services).
INDUSTRY_TEMPLATE_APPLYING_EVENT_KEY = "industry.template.applying"

# TenantSetting keys (admin-owned table, written directly by the loader under system_context).
# Terminology overrides are stored as one JSON map under this key; the UI reads it via
# queries.terminology_for(tenant). Module toggles are one JSON map under the toggles key.
TERMINOLOGY_SETTING_KEY = "industry.terminology"
MODULE_TOGGLES_SETTING_KEY = "industry.module_toggles"

# Permissions (D-009): one key per guarded endpoint action.
INDUSTRY_TEMPLATE_READ = "industry.template.read"
INDUSTRY_TEMPLATE_APPLY = "industry.template.apply"
# Creating a WHOLE new tenant is a platform/system action, not a tenant-admin one (PLAN 14.2 /
# D-061). Platform operators hold this key; a tenant admin does not, so onboarding cannot be used
# to spin up arbitrary tenants from an ordinary tenant login.
ONBOARDING_TENANT_CREATE = "onboarding.tenant.create"

register_permissions(
    INDUSTRY_TEMPLATE_READ,
    INDUSTRY_TEMPLATE_APPLY,
    ONBOARDING_TENANT_CREATE,
    descriptions={
        INDUSTRY_TEMPLATE_READ: "Read the shipped industry templates and their parsed content",
        INDUSTRY_TEMPLATE_APPLY: "Apply an industry template to a tenant at provisioning",
        ONBOARDING_TENANT_CREATE: "Provision a new tenant (platform operators only)",
    },
)
