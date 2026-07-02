"""Admin module — tenant administration. Owns the tenancy root + per-tenant settings
(models.py) and the user/role provisioning service (service.py); PLAN 14.3 adds the
tenant-admin API (router.py + schemas.py + queries.py): user/role management, the
read-only audit viewer, and the read-only number-sequence viewer — all over EXISTING
core tables (no new table, no migration). The admin permission keys are core RBAC keys
declared in core/rbac.py (registered + seeded there); this package imports core + its own
service/queries ONLY, never another module's service (STRUCTURE §5). Exchange rates and
tax codes are managed by the FINANCE module's endpoints, not re-exposed here."""
