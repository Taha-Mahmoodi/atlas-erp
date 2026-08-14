"""PLAN 19.1 (Phase 19 Task 2): the hospitality module is WIRED, not merely present on disk.

D-009 is the whole point of this file: a tenant may only be granted permission keys the CODE
declares, and a key only reaches ``catalog_keys()`` if something imports the owning module's
``constants.py`` at app-import time. The import hook is the router mount in ``core/bootstrap.py`` —
the same wiring every other module uses. This module therefore deliberately does NOT import
``app.modules.hospitality`` itself: the keys must arrive via ``tests/conftest.py``'s
``from app.main import create_app``, so a missing bootstrap mount fails here instead of silently
shipping keys no tenant can ever be granted.

``DEPLETE_TICKET_JOB`` is asserted as a value, not a name: Task 5 registers the depletion handler
under it and Task 8 documents it, so a rename is a cross-task break, not a local one.
"""

import pytest

from app.core.rbac import catalog_keys

HOSPITALITY_PERMISSION_KEYS = (
    "hospitality.menu.read",
    "hospitality.menu.manage",
    "hospitality.ticket.read",
    "hospitality.ticket.manage",
    "hospitality.ticket.settle",
)


@pytest.mark.parametrize("key", HOSPITALITY_PERMISSION_KEYS)
def test_hospitality_permission_key_is_in_the_catalog(key: str) -> None:
    """D-009: a tenant can only be granted keys code declares — and only a mounted module declares
    them, because the mount is what imports constants.py."""
    assert key in catalog_keys()


def test_the_depletion_job_key_is_declared() -> None:
    """Task 5 registers the background depletion handler under this exact key (Q4)."""
    from app.modules.hospitality.constants import DEPLETE_TICKET_JOB

    assert DEPLETE_TICKET_JOB == "hospitality.deplete_ticket"
