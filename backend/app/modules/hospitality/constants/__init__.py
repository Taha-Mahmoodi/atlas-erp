"""Hospitality constants package (STRUCTURE §3/§8.4).

A single ``constants.py`` reached the 400-line cap once Phase 20's rooms enums, permissions and
document constants were added to Phase 19's ordering set and Phase 21's reservation set. Split by
KIND rather than by phase — the ``sales/constants/`` and ``finance/constants/`` precedent, both of
which made the same move at the same cap:

- ``enums``: every status/lifecycle StrEnum with its transition table, plus the numeric defaults.
- ``permissions``: the ``hospitality.*`` keys, registered into the RBAC catalog AT IMPORT (D-009).
- ``documents``: doc types, number sequences, docflow link types, domain-event keys, job keys.

Everything is re-exported here, so every existing ``from app.modules.hospitality.constants import
X`` keeps working from ONE surface and no caller had to change. Importing this package is also what
registers the permission catalog entries — the module ``__init__`` imports it for exactly that
reason, and ``register_permissions`` is idempotent, so a second importer costs nothing.
"""

from app.modules.hospitality.constants.documents import (
    DEPLETE_TICKET_JOB,
    HOUSEKEEPING_TASK_DOC_TYPE,
    HOUSEKEEPING_TASK_NUMBER_PADDING,
    HOUSEKEEPING_TASK_NUMBER_PREFIX,
    HOUSEKEEPING_TASK_SEQUENCE_NAME,
    HOUSEKEEPING_TRIGGERED_BY_LINK,
    ORDER_TICKET_DOC_TYPE,
    ORDER_TICKET_FIRED_EVENT_KEY,
    ORDER_TICKET_NUMBER_PADDING,
    ORDER_TICKET_NUMBER_PREFIX,
    ORDER_TICKET_SEQUENCE_NAME,
    ORDER_TICKET_SETTLED_EVENT_KEY,
    RESERVATION_SEATED_AS_TICKET_LINK,
    TABLE_RESERVATION_DOC_TYPE,
    TABLE_RESERVATION_NUMBER_PADDING,
    TABLE_RESERVATION_NUMBER_PREFIX,
    TABLE_RESERVATION_SEQUENCE_NAME,
    TICKET_DEPLETED_BY_MOVE_LINK,
    TICKET_INGREDIENTS_CONSUMED_EVENT_KEY,
)
from app.modules.hospitality.constants.enums import (
    AT_RISK_DEFAULT_THRESHOLD,
    DEFAULT_BOOKING_HORIZON_DAYS,
    DEFAULT_COVERS_MAX,
    DEFAULT_MAX_PARTY,
    DEFAULT_MIN_PARTY,
    DEFAULT_PARTIES_MAX,
    DEFAULT_SERVICE_CLOSE,
    DEFAULT_SERVICE_OPEN,
    DEPLETE_MAX_COMPONENTS_PER_JOB,
    HOUSEKEEPING_FLOW,
    HOUSEKEEPING_TASK_FLOW,
    HOUSEKEEPING_UNSELLABLE,
    RESERVATION_FLOW,
    SLOT_MINUTES,
    TICKET_FLOW,
    TICKET_PROGRESS_STATES,
    AvailabilitySource,
    AvailabilityState,
    HousekeepingStatus,
    HousekeepingTaskStatus,
    HousekeepingTrigger,
    OrderTicketStatus,
    ReservationStatus,
)
from app.modules.hospitality.constants.permissions import (
    HOSPITALITY_HOUSEKEEPING_MANAGE,
    HOSPITALITY_MENU_MANAGE,
    HOSPITALITY_MENU_READ,
    HOSPITALITY_RESERVATION_BOOK,
    HOSPITALITY_RESERVATION_MANAGE,
    HOSPITALITY_RESERVATION_READ,
    HOSPITALITY_ROOMS_MANAGE,
    HOSPITALITY_ROOMS_READ,
    HOSPITALITY_TICKET_MANAGE,
    HOSPITALITY_TICKET_READ,
    HOSPITALITY_TICKET_SETTLE,
)

__all__ = [
    "AT_RISK_DEFAULT_THRESHOLD",
    "DEFAULT_BOOKING_HORIZON_DAYS",
    "DEFAULT_COVERS_MAX",
    "DEFAULT_MAX_PARTY",
    "DEFAULT_MIN_PARTY",
    "DEFAULT_PARTIES_MAX",
    "DEFAULT_SERVICE_CLOSE",
    "DEFAULT_SERVICE_OPEN",
    "DEPLETE_MAX_COMPONENTS_PER_JOB",
    "DEPLETE_TICKET_JOB",
    "HOSPITALITY_HOUSEKEEPING_MANAGE",
    "HOSPITALITY_MENU_MANAGE",
    "HOSPITALITY_MENU_READ",
    "HOSPITALITY_RESERVATION_BOOK",
    "HOSPITALITY_RESERVATION_MANAGE",
    "HOSPITALITY_RESERVATION_READ",
    "HOSPITALITY_ROOMS_MANAGE",
    "HOSPITALITY_ROOMS_READ",
    "HOSPITALITY_TICKET_MANAGE",
    "HOSPITALITY_TICKET_READ",
    "HOSPITALITY_TICKET_SETTLE",
    "HOUSEKEEPING_FLOW",
    "HOUSEKEEPING_TASK_DOC_TYPE",
    "HOUSEKEEPING_TASK_FLOW",
    "HOUSEKEEPING_TASK_NUMBER_PADDING",
    "HOUSEKEEPING_TASK_NUMBER_PREFIX",
    "HOUSEKEEPING_TASK_SEQUENCE_NAME",
    "HOUSEKEEPING_TRIGGERED_BY_LINK",
    "HOUSEKEEPING_UNSELLABLE",
    "ORDER_TICKET_DOC_TYPE",
    "ORDER_TICKET_FIRED_EVENT_KEY",
    "ORDER_TICKET_NUMBER_PADDING",
    "ORDER_TICKET_NUMBER_PREFIX",
    "ORDER_TICKET_SEQUENCE_NAME",
    "ORDER_TICKET_SETTLED_EVENT_KEY",
    "RESERVATION_FLOW",
    "RESERVATION_SEATED_AS_TICKET_LINK",
    "SLOT_MINUTES",
    "TABLE_RESERVATION_DOC_TYPE",
    "TABLE_RESERVATION_NUMBER_PADDING",
    "TABLE_RESERVATION_NUMBER_PREFIX",
    "TABLE_RESERVATION_SEQUENCE_NAME",
    "TICKET_DEPLETED_BY_MOVE_LINK",
    "TICKET_FLOW",
    "TICKET_INGREDIENTS_CONSUMED_EVENT_KEY",
    "TICKET_PROGRESS_STATES",
    "AvailabilitySource",
    "AvailabilityState",
    "HousekeepingStatus",
    "HousekeepingTaskStatus",
    "HousekeepingTrigger",
    "OrderTicketStatus",
    "ReservationStatus",
]
