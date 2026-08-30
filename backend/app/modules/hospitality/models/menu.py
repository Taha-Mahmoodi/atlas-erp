"""The restaurant's own MENU structure: sections, a dish's place in them, and free tags (#212).

One file of the ``models/`` package rather than more of ``ordering.py``, because what lives here is
one concept: how a property ORGANISES the dishes it sells, which is a different concern from the
availability and ticket state next door. It was a ``menu_models.py`` sibling while hospitality still
had a single ``models.py`` at the 400-line cap (#176); the package is that workaround's proper home,
and moving it in is also what puts these three tables on the ``Base.metadata`` that
``alembic/env.py`` autogenerates against — the sibling was reachable only through the router.

**Why hospitality owns this and inventory does not.** A dish is an ordinary ``Item`` and its
``ItemCategory`` decides how it is VALUED — costing method, inventory/COGS/price-difference
accounts. That is accounting structure, shared by every industry, and it is the wrong axis for a
menu: forcing "Starters" to be an item category would demand GL accounts for a course, and forcing
"Italian" into the same tree would demand a dish belong to exactly one of them. So the menu is
modelled HERE, keyed by ``item_id`` (an opaque id, D-029), and inventory is untouched —
hospitality already reads inventory downward and the reverse import is forbidden (STRUCTURE §5).

**Two axes, because a restaurant has two.** Sections are a TREE and a dish sits in exactly one
(Starters > Cold, Main courses > Grill): that is the running order of a printed menu, and order
implies a single place. Tags are FLAT and a dish carries any number (vegan, spicy, gluten-free,
Italian): they answer "show me everything vegan", which a tree cannot without duplicating dishes.
Collapsing either into the other was rejected in D-081.
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

# How deep the section tree may go. Two levels is what a menu actually uses (a course, optionally
# split), and a bound is what stops a reparent from building a chain nothing can render.
MAX_SECTION_DEPTH = 3


class MenuSection(UuidPKMixin, TenantMixin, AuditMixin, TimestampMixin, Base):
    """One heading on the menu — a course, or a sub-heading under one.

    Audited (D-010), unlike the availability row next door: a section is slow-changing structure a
    property sets up once and edits rarely, which is exactly the shape ``AuditMixin`` is for. The
    86 board is the opposite (dozens of flips a night) and is deliberately not audited.

    ``sort_order`` is the property's own running order, not alphabetical: desserts come last on a
    menu because the restaurant says so. Ties fall back to ``name`` so the list is never unstable.
    """

    __tablename__ = "hsp_menu_sections"
    __table_args__ = (
        tenant_unique(),
        tenant_fk("adm_tenants"),
        # A section's parent must be a section in the SAME tenant, enforced by the database
        # (D-007 item 4) rather than by whoever writes the next query.
        sa.ForeignKeyConstraint(
            ["tenant_id", "parent_id"],
            ["hsp_menu_sections.tenant_id", "hsp_menu_sections.id"],
            name="fk_hsp_menu_sections_parent",
        ),
        # One heading of a given name per parent. Two "Cold" sub-sections under one course is a
        # mistake every time; two under DIFFERENT courses is normal, so the parent is in the key.
        sa.UniqueConstraint(
            "tenant_id", "parent_id", "name", name="uq_hsp_menu_sections_tenant_parent_name"
        ),
        # PERFORMANCE §1: the tree read is "every section of this tenant in order", and the child
        # lookup on a delete/reparent is by parent.
        sa.Index("ix_hsp_menu_sections_tenant_id_parent_id", "tenant_id", "parent_id"),
    )

    name: Mapped[str] = mapped_column(sa.String(80), nullable=False)
    parent_id: Mapped[uuid.UUID | None] = mapped_column(sa.Uuid, nullable=True)
    # The server default is a plain string rather than a Core SQL expression: the D-007 grep gate
    # bans those anywhere under app/modules/ (it reads source, so even naming one in a comment
    # trips it), and every other module model writes an integer default the same way.
    sort_order: Mapped[int] = mapped_column(
        sa.Integer, nullable=False, default=0, server_default="0"
    )


class MenuPlacement(UuidPKMixin, TenantMixin, TimestampMixin, Base):
    """WHERE a dish sits on the menu — at most one section per dish.

    A link table rather than a column, because the column would have to live on ``inv_items``,
    which belongs to inventory. ``item_id`` carries no FK (D-029, the opaque-id rule every
    cross-module reference in Atlas follows); the service validates the item exists through
    ``inventory/queries.existing_item_ids`` before writing, which IS the referential integrity.

    A dish with no row is simply unplaced — it still sells, it just has no heading. Absence being
    the default is the same call ``MenuAvailability`` makes, and for the same reason: the common
    state should cost no rows.
    """

    __tablename__ = "hsp_menu_placements"
    __table_args__ = (
        tenant_unique(),
        tenant_fk("adm_tenants"),
        sa.ForeignKeyConstraint(
            ["tenant_id", "section_id"],
            ["hsp_menu_sections.tenant_id", "hsp_menu_sections.id"],
            name="fk_hsp_menu_placements_section",
        ),
        # ONE section per dish — the constraint that makes "a dish sits in exactly one place" a
        # database fact instead of a service convention.
        sa.UniqueConstraint("tenant_id", "item_id", name="uq_hsp_menu_placements_tenant_item"),
        sa.Index("ix_hsp_menu_placements_tenant_id_section_id", "tenant_id", "section_id"),
    )

    item_id: Mapped[uuid.UUID] = mapped_column(sa.Uuid, nullable=False)
    section_id: Mapped[uuid.UUID] = mapped_column(sa.Uuid, nullable=False)


class MenuItemTag(UuidPKMixin, TenantMixin, TimestampMixin, Base):
    """One free label on one dish: vegan, spicy, Italian, gluten-free.

    The tag is the STRING, with no tag-master table behind it. A master would buy renaming and a
    guaranteed spelling, and cost a second entity, a second CRUD surface and a join on every read —
    for something a property types a dozen of. The set a tenant uses is ``SELECT DISTINCT tag``,
    renaming is one ``UPDATE``, and the unique constraint below stops the same label landing twice
    on one dish. Revisit if tags ever need colours, ordering or descriptions (YAGNI, D-081).

    Stored lower-cased and trimmed by the service so "Vegan" and "vegan" cannot both exist.
    """

    __tablename__ = "hsp_menu_item_tags"
    __table_args__ = (
        tenant_unique(),
        tenant_fk("adm_tenants"),
        sa.UniqueConstraint(
            "tenant_id", "item_id", "tag", name="uq_hsp_menu_item_tags_tenant_item_tag"
        ),
        # The filter this table exists to serve: every dish carrying a tag.
        sa.Index("ix_hsp_menu_item_tags_tenant_id_tag", "tenant_id", "tag"),
    )

    item_id: Mapped[uuid.UUID] = mapped_column(sa.Uuid, nullable=False)
    tag: Mapped[str] = mapped_column(sa.String(40), nullable=False)


__all__ = ["MAX_SECTION_DEPTH", "MenuItemTag", "MenuPlacement", "MenuSection"]
