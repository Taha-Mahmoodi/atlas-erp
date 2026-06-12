"""rbac

Revision ID: 0004
Revises: 0003
Create Date: 2026-06-12

RBAC tables per D-009:
- core_permissions: GLOBAL code-defined catalog (not tenant-scoped), key UNIQUE.
- core_roles: tenant-scoped roles, UNIQUE(tenant_id, name), D-007 FK backstop.
- core_role_permissions: role(tenant composite FK) -> permission(global FK).
- core_user_roles: user(tenant composite FK) -> role(tenant composite FK).
Constraint names are spelled out per the D-022 naming convention so SQLite batch mode
can drop them later; DDL is portable across SQLite and Postgres.
"""

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "0004"
down_revision: str | None = "0003"
branch_labels: str | None = None
depends_on: str | None = None


def upgrade() -> None:
    op.create_table(
        "core_permissions",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("key", sa.String(length=150), nullable=False),
        sa.Column("description", sa.String(length=300), nullable=True),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_core_permissions")),
        sa.UniqueConstraint("key", name=op.f("uq_core_permissions_key")),
    )

    op.create_table(
        "core_roles",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("tenant_id", sa.Uuid(), nullable=False),
        sa.Column("name", sa.String(length=100), nullable=False),
        sa.Column("description", sa.String(length=300), nullable=True),
        sa.Column("is_system", sa.Boolean(), server_default=sa.false(), nullable=False),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.Column(
            "updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.ForeignKeyConstraint(
            ["tenant_id"],
            ["adm_tenants.id"],
            name=op.f("fk_core_roles_tenant_id_adm_tenants"),
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_core_roles")),
        sa.UniqueConstraint("tenant_id", "name", name="uq_core_roles_tenant_id_name"),
        sa.UniqueConstraint("tenant_id", "id", name=op.f("uq_core_roles_tenant_id")),
    )
    op.create_index(op.f("ix_core_roles_tenant_id"), "core_roles", ["tenant_id"])

    op.create_table(
        "core_role_permissions",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("tenant_id", sa.Uuid(), nullable=False),
        sa.Column("role_id", sa.Uuid(), nullable=False),
        sa.Column("permission_id", sa.Uuid(), nullable=False),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.Column(
            "updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.ForeignKeyConstraint(
            ["tenant_id"],
            ["adm_tenants.id"],
            name=op.f("fk_core_role_permissions_tenant_id_adm_tenants"),
        ),
        sa.ForeignKeyConstraint(
            ["tenant_id", "role_id"],
            ["core_roles.tenant_id", "core_roles.id"],
            name=op.f("fk_core_role_permissions_tenant_id_core_roles"),
        ),
        sa.ForeignKeyConstraint(
            ["permission_id"],
            ["core_permissions.id"],
            name=op.f("fk_core_role_permissions_permission_id_core_permissions"),
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_core_role_permissions")),
        sa.UniqueConstraint(
            "tenant_id",
            "role_id",
            "permission_id",
            name="uq_core_role_permissions_tenant_id_role_id_permission_id",
        ),
        sa.UniqueConstraint(
            "tenant_id", "id", name=op.f("uq_core_role_permissions_tenant_id")
        ),
    )
    op.create_index(
        op.f("ix_core_role_permissions_tenant_id"), "core_role_permissions", ["tenant_id"]
    )

    op.create_table(
        "core_user_roles",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("tenant_id", sa.Uuid(), nullable=False),
        sa.Column("user_id", sa.Uuid(), nullable=False),
        sa.Column("role_id", sa.Uuid(), nullable=False),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.Column(
            "updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.ForeignKeyConstraint(
            ["tenant_id"],
            ["adm_tenants.id"],
            name=op.f("fk_core_user_roles_tenant_id_adm_tenants"),
        ),
        sa.ForeignKeyConstraint(
            ["tenant_id", "user_id"],
            ["core_users.tenant_id", "core_users.id"],
            name=op.f("fk_core_user_roles_tenant_id_core_users"),
        ),
        sa.ForeignKeyConstraint(
            ["tenant_id", "role_id"],
            ["core_roles.tenant_id", "core_roles.id"],
            name=op.f("fk_core_user_roles_tenant_id_core_roles"),
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_core_user_roles")),
        sa.UniqueConstraint(
            "tenant_id", "user_id", "role_id", name="uq_core_user_roles_tenant_id_user_id_role_id"
        ),
        sa.UniqueConstraint("tenant_id", "id", name=op.f("uq_core_user_roles_tenant_id")),
    )
    op.create_index(op.f("ix_core_user_roles_tenant_id"), "core_user_roles", ["tenant_id"])


def downgrade() -> None:
    op.drop_index(op.f("ix_core_user_roles_tenant_id"), table_name="core_user_roles")
    op.drop_table("core_user_roles")
    op.drop_index(
        op.f("ix_core_role_permissions_tenant_id"), table_name="core_role_permissions"
    )
    op.drop_table("core_role_permissions")
    op.drop_index(op.f("ix_core_roles_tenant_id"), table_name="core_roles")
    op.drop_table("core_roles")
    op.drop_table("core_permissions")
