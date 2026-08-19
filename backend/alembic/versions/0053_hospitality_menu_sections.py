"""hospitality menu sections, placements and tags

Revision ID: 0053
Revises: 0052
Create Date: 2026-08-17

Issue #212 / D-081 — the restaurant's own menu STRUCTURE, which Atlas had no room for: a dish's
only grouping was its item category, and that category decides how the dish is VALUED (costing
method, inventory/COGS/price-difference accounts). Menu structure is a different axis, and it is
two axes rather than one: a tree of sections a dish sits in exactly one of, and flat tags it
carries any number of.

Three tables, all owned by hospitality and keyed on ``item_id`` as an opaque id (D-029), so
inventory is untouched — hospitality reads inventory downward and the reverse import is forbidden
(STRUCTURE §5).

- ``hsp_menu_sections``: the tree. Self-referencing COMPOSITE FK (tenant_id, parent_id) so a
  section's parent can only ever be a section in the same tenant (D-007 item 4). Unique on
  (tenant, parent, name): two "Cold" sub-headings under one course is always a mistake, under two
  different courses is normal.
- ``hsp_menu_placements``: unique on (tenant, item) — "a dish sits in exactly one place" as a
  database fact rather than a service convention.
- ``hsp_menu_item_tags``: the tag is the string, no master table (D-081). Unique on
  (tenant, item, tag); indexed on (tenant, tag), which is the filter the flat shape exists for.

All DDL is portable across SQLite and Postgres and every identifier is <= 63 chars (PG cap). No
existing table is altered, so no trigger recreation is involved (D-022).
"""

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "0053"
down_revision: str | None = "0052"
branch_labels: str | None = None
depends_on: str | None = None


def upgrade() -> None:
    op.create_table(
        "hsp_menu_sections",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("tenant_id", sa.Uuid(), nullable=False),
        sa.Column("name", sa.String(length=80), nullable=False),
        sa.Column("parent_id", sa.Uuid(), nullable=True),
        sa.Column("sort_order", sa.Integer(), nullable=False, server_default=sa.text("0")),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("tenant_id", "id"),
        sa.UniqueConstraint(
            "tenant_id", "parent_id", "name", name="uq_hsp_menu_sections_tenant_parent_name"
        ),
        sa.ForeignKeyConstraint(["tenant_id"], ["adm_tenants.id"]),
        sa.ForeignKeyConstraint(
            ["tenant_id", "parent_id"],
            ["hsp_menu_sections.tenant_id", "hsp_menu_sections.id"],
            name="fk_hsp_menu_sections_parent",
        ),
    )
    op.create_index("ix_hsp_menu_sections_tenant_id", "hsp_menu_sections", ["tenant_id"])
    op.create_index(
        "ix_hsp_menu_sections_tenant_id_parent_id",
        "hsp_menu_sections",
        ["tenant_id", "parent_id"],
    )

    op.create_table(
        "hsp_menu_placements",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("tenant_id", sa.Uuid(), nullable=False),
        sa.Column("item_id", sa.Uuid(), nullable=False),
        sa.Column("section_id", sa.Uuid(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("tenant_id", "id"),
        sa.UniqueConstraint("tenant_id", "item_id", name="uq_hsp_menu_placements_tenant_item"),
        sa.ForeignKeyConstraint(["tenant_id"], ["adm_tenants.id"]),
        sa.ForeignKeyConstraint(
            ["tenant_id", "section_id"],
            ["hsp_menu_sections.tenant_id", "hsp_menu_sections.id"],
            name="fk_hsp_menu_placements_section",
        ),
    )
    op.create_index("ix_hsp_menu_placements_tenant_id", "hsp_menu_placements", ["tenant_id"])
    op.create_index(
        "ix_hsp_menu_placements_tenant_id_section_id",
        "hsp_menu_placements",
        ["tenant_id", "section_id"],
    )

    op.create_table(
        "hsp_menu_item_tags",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("tenant_id", sa.Uuid(), nullable=False),
        sa.Column("item_id", sa.Uuid(), nullable=False),
        sa.Column("tag", sa.String(length=40), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("tenant_id", "id"),
        sa.UniqueConstraint(
            "tenant_id", "item_id", "tag", name="uq_hsp_menu_item_tags_tenant_item_tag"
        ),
        sa.ForeignKeyConstraint(["tenant_id"], ["adm_tenants.id"]),
    )
    op.create_index("ix_hsp_menu_item_tags_tenant_id", "hsp_menu_item_tags", ["tenant_id"])
    op.create_index(
        "ix_hsp_menu_item_tags_tenant_id_tag", "hsp_menu_item_tags", ["tenant_id", "tag"]
    )


def downgrade() -> None:
    op.drop_index("ix_hsp_menu_item_tags_tenant_id_tag", table_name="hsp_menu_item_tags")
    op.drop_index("ix_hsp_menu_item_tags_tenant_id", table_name="hsp_menu_item_tags")
    op.drop_table("hsp_menu_item_tags")
    op.drop_index(
        "ix_hsp_menu_placements_tenant_id_section_id", table_name="hsp_menu_placements"
    )
    op.drop_index("ix_hsp_menu_placements_tenant_id", table_name="hsp_menu_placements")
    op.drop_table("hsp_menu_placements")
    op.drop_index("ix_hsp_menu_sections_tenant_id_parent_id", table_name="hsp_menu_sections")
    op.drop_index("ix_hsp_menu_sections_tenant_id", table_name="hsp_menu_sections")
    op.drop_table("hsp_menu_sections")
