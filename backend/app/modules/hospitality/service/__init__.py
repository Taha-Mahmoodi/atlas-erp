"""Hospitality service package (STRUCTURE §3: one file per aggregate, each <400 lines).

Split from the start rather than at the cap: PLAN 19 puts three independent aggregates in this
module — menu availability (Task 3), the order-ticket lifecycle (Task 4) and background ingredient
depletion (Task 5) — and Q2 alone budgets ~150 lines for availability, so a single ``service.py``
would breach the 400-line cap inside the same phase and force a rename commit (STRUCTURE §8.10).

Re-exported here so callers use one import (``from app.modules.hospitality import service`` then
``service.set_availability(...)``), the inventory/finance service-package precedent.
"""

from app.modules.hospitality.service.availability import (
    MenuItemAvailability,
    availability_for_items,
    clear_86,
    decrement_remaining,
    set_availability,
)

__all__ = [
    "MenuItemAvailability",
    "availability_for_items",
    "clear_86",
    "decrement_remaining",
    "set_availability",
]
