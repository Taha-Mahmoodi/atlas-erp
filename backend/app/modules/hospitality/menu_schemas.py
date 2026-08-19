"""Wire shapes for the menu structure (#212, D-081) — a sibling of ``schemas.py``, which is the
availability/ticket/website surface and already carries its own file's worth.

Staff shapes first, then the one shape the WEBSITE reads, matching the section rule ``schemas.py``
follows.
"""

import uuid

from pydantic import Field

from app.core.schemas import ApiModel


class MenuSectionCreate(ApiModel):
    """Add a heading. ``parent_id`` absent means a root section — a course rather than a
    sub-heading under one."""

    name: str = Field(min_length=1, max_length=80)
    parent_id: uuid.UUID | None = None
    sort_order: int = Field(default=0, ge=0, le=9999)


class MenuSectionUpdate(ApiModel):
    """Rename, reorder, or move a section. Every field is optional; the ones absent are left
    alone.

    ``parent_id`` needs ``reparent`` beside it because a nullable optional field cannot say the
    difference between "do not touch the parent" and "make this a root section" — the standard
    PATCH ambiguity, answered with a flag rather than a magic value."""

    name: str | None = Field(default=None, min_length=1, max_length=80)
    parent_id: uuid.UUID | None = None
    reparent: bool = False
    sort_order: int | None = Field(default=None, ge=0, le=9999)


class MenuSectionRead(ApiModel):
    """One heading, plus how many dishes sit directly in it.

    ``dish_count`` is DIRECT, not cumulative: a parent showing its children's dishes would read as
    "12 starters" on a section that holds none of them itself, and the client already has the tree
    to add them up if it wants to."""

    id: uuid.UUID
    name: str
    parent_id: uuid.UUID | None = None
    sort_order: int
    dish_count: int = 0


class MenuPlacementSet(ApiModel):
    """Where a dish sits and what it is labelled — REPLACED together (one screen, one call).

    ``section_id: null`` unplaces the dish; ``tags: []`` clears its labels. Tags are trimmed,
    lower-cased and de-duplicated by the service, so "Vegan" and "vegan " are one label."""

    section_id: uuid.UUID | None = None
    tags: list[str] = Field(default_factory=list)


class MenuPlacementRead(ApiModel):
    """A dish's menu placement as stored, after cleaning."""

    item_id: uuid.UUID
    section_id: uuid.UUID | None = None
    tags: list[str] = Field(default_factory=list)


# --- The website surface ------------------------------------------------------


class MenuPlacementsRead(ApiModel):
    """Where every placed dish sits and what it is labelled — the whole map in one answer.

    **Why this is its own read rather than fields on ``GET /menu``.** That endpoint is budgeted at
    exactly THREE statements (PERFORMANCE §2, pinned by `test_query_budgets.py`) and it is already
    spending them on auth, the item page and the price resolution; hanging placement and tags off
    it would have cost three more. Splitting also follows the argument the module already makes
    about cache policy: menu STRUCTURE changes when a manager rewrites the menu, price changes on
    a reprice and availability changes when a table orders the last portion. Three lifetimes, three
    resources — a website fetches this one rarely and holds it.

    Dishes with neither a section nor a tag are simply absent: unplaced and unlabelled is the
    default, so it costs no row here either.
    """

    items: list["MenuPlacementRead"]


__all__ = [
    "MenuPlacementRead",
    "MenuPlacementsRead",
    "MenuPlacementSet",
    "MenuSectionCreate",
    "MenuSectionRead",
    "MenuSectionUpdate",
]
