"""Hospitality service package (STRUCTURE §3: one file per aggregate, each <400 lines).

Split from the start rather than at the cap: PLAN 19 puts three independent aggregates in this
module — menu availability (Task 3), the order-ticket lifecycle (Task 4) and background ingredient
depletion (Task 5) — and Q2 alone budgets ~150 lines for availability, so a single ``service.py``
would breach the 400-line cap inside the same phase and force a rename commit (STRUCTURE §8.10).

Re-exported here so callers use one import (``from app.modules.hospitality import service`` then
``service.set_availability(...)``), the inventory/finance service-package precedent.
"""

# ``depletion`` is imported for its @register_job side effect as well as its exports: a job type
# exists in core/jobs.py's registry because a handler for it is in the codebase (the count_jobs
# precedent in inventory/service/__init__.py), and submit_job rejects an unregistered type.
from app.modules.hospitality.service.availability import (
    MenuItemAvailability,
    availability_for_items,
    clear_86,
    decrement_remaining,
    resolve,
    set_availability,
)
from app.modules.hospitality.service.depletion import (
    ComponentDemand,
    aggregate_components,
    deplete_ticket,
    deplete_ticket_job,
    take_depletion_jobs,
)
from app.modules.hospitality.service.tickets import (
    add_lines,
    advance_ticket,
    create_ticket,
    fire_ticket,
    get_ticket,
    get_ticket_lines,
    settle_ticket,
)

__all__ = [
    "ComponentDemand",
    "MenuItemAvailability",
    "add_lines",
    "advance_ticket",
    "aggregate_components",
    "availability_for_items",
    "clear_86",
    "create_ticket",
    "decrement_remaining",
    "deplete_ticket",
    "deplete_ticket_job",
    "fire_ticket",
    "get_ticket",
    "get_ticket_lines",
    "resolve",
    "set_availability",
    "take_depletion_jobs",
    "settle_ticket",
]
