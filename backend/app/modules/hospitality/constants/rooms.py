"""The HOTEL's enums, lifecycle transition tables and numeric defaults (PLAN 20.1/20.2).

Split out of ``enums.py`` when Phase 20.2's room-reservation lifecycle took that file past the
STRUCTURE §8.4 400-line cap — the same seam ``models/rooms.py`` and ``service/rooms.py`` already
cut, and a real one rather than an arithmetic one: ``enums.py`` now holds the RESTAURANT's
vocabulary (the order ticket, the menu, the table booking's 15-minute pacing) and this file holds
the PROPERTY's (the physical room's condition, the housekeeping work order, the room booking's
allotment). The two share a module and nothing else, which is the naming decision D-087 records.

Each lifecycle keeps its transition rule NEXT TO its enum, the rule ``enums.py`` states: the legal
moves are the contract rather than the membership. Everything here is re-exported from the package
``__init__``, so every ``from app.modules.hospitality.constants import X`` is unchanged.
"""

from enum import StrEnum


class HousekeepingStatus(StrEnum):
    """What state a PHYSICAL room is in. A column on the ROOM, not on a task.

    The room is what is sellable or not, so the state has to live on the room: a task is a work
    order that may not exist (a manager can mark a room clean without one) and may be cancelled,
    while the room's condition is always true of it. ``HousekeepingTaskStatus`` below is that work
    order's own progress, and the two are kept in step by ``service/housekeeping.py`` routing every
    room-state change through ONE function — never by writing the column twice.

    - **DIRTY** — the guest has gone, the room needs making up. The state a checkout leaves behind,
      and the state a room returns to from out of order.
    - **IN_PROGRESS** — an attendant is in the room.
    - **CLEAN** — made up, sellable.
    - **INSPECTED** — a supervisor has checked it. A property that does not inspect simply never
      uses the state; one that does gates arrivals on it. Both are ordinary.
    - **OUT_OF_ORDER** — not sellable at all: a burst pipe, a refit. This is the one state with a
      revenue consequence, and Phase 20 Task 4 hangs it off the allotment counter — a room out of
      order lowers ``rooms_sellable`` on the future dates it covers, and coming back raises it. The
      hook belongs in ``rooms.set_housekeeping_status``, which is why every path that moves this
      column goes through that one function.
    """

    DIRTY = "DIRTY"
    IN_PROGRESS = "IN_PROGRESS"
    CLEAN = "CLEAN"
    INSPECTED = "INSPECTED"
    OUT_OF_ORDER = "OUT_OF_ORDER"


# The legal moves, one frozenset per state — the ``RESERVATION_FLOW`` shape, written out because a
# housekeeping cycle branches rather than marching. No state is terminal: a room is reused forever.
#
# OUT_OF_ORDER is reachable from EVERYWHERE (a pipe bursts whatever the room's condition was) and
# leaves only to DIRTY: a room that has been out of service is not sellable on a supervisor's word,
# it is cleaned first. CLEAN and INSPECTED fall back to DIRTY, which is the ordinary checkout.
#
# CLEAN and INSPECTED also go back to IN_PROGRESS, and that edge is what makes the two NON-CHECKOUT
# triggers work: a GUEST_REQUEST arrives mid-stay on a room that is CLEAN and a SCHEDULED stayover
# service lands on one a supervisor has INSPECTED, so without it those tasks could be RAISED and
# never STARTED and only the departure clean would function. An attendant standing in a made-up
# room IS the IN_PROGRESS fact, and coming back out lands on CLEAN — never straight back to
# INSPECTED, because somebody has been in the room since it was signed off. DIRTY -> CLEAN is still
# absent, so nothing here lets a room be declared clean without an attendant in it.
HOUSEKEEPING_FLOW: dict[HousekeepingStatus, frozenset[HousekeepingStatus]] = {
    HousekeepingStatus.DIRTY: frozenset(
        {HousekeepingStatus.IN_PROGRESS, HousekeepingStatus.OUT_OF_ORDER}
    ),
    HousekeepingStatus.IN_PROGRESS: frozenset(
        {HousekeepingStatus.CLEAN, HousekeepingStatus.DIRTY, HousekeepingStatus.OUT_OF_ORDER}
    ),
    HousekeepingStatus.CLEAN: frozenset(
        {
            HousekeepingStatus.IN_PROGRESS,
            HousekeepingStatus.INSPECTED,
            HousekeepingStatus.DIRTY,
            HousekeepingStatus.OUT_OF_ORDER,
        }
    ),
    HousekeepingStatus.INSPECTED: frozenset(
        {
            HousekeepingStatus.IN_PROGRESS,
            HousekeepingStatus.DIRTY,
            HousekeepingStatus.OUT_OF_ORDER,
        }
    ),
    HousekeepingStatus.OUT_OF_ORDER: frozenset({HousekeepingStatus.DIRTY}),
}

# The states in which a room may NOT be sold. Declared here with no consumer YET and that is
# deliberate: it is the contract PLAN 20.2's ``rooms_sellable`` count and
# ``rooms.set_housekeeping_status``'s counter hook must both read, and a set each of them derived
# for itself is exactly how an oversell gets in. D-085 names it; 20.2 is what imports it.
HOUSEKEEPING_UNSELLABLE: frozenset[HousekeepingStatus] = frozenset(
    {HousekeepingStatus.OUT_OF_ORDER}
)


class HousekeepingTrigger(StrEnum):
    """WHY a housekeeping task exists — stored on the task, never inferred.

    A departure clean, a planned service and a guest's mid-stay request produce identical work and
    are counted separately by every property that measures housekeeping; the reservation that
    caused a CHECKOUT task is off the board by the time anybody asks.

    - **CHECKOUT** — the departure clean, the bulk of the day's work. Task 4's check-out raises it
      and passes the reservation's document id, so the chain reads reservation -> task.
    - **SCHEDULED** — a stayover service or a deep clean the property planned.
    - **GUEST_REQUEST** — the guest asked, mid-stay.
    """

    CHECKOUT = "CHECKOUT"
    SCHEDULED = "SCHEDULED"
    GUEST_REQUEST = "GUEST_REQUEST"


class HousekeepingTaskStatus(StrEnum):
    """The work order's own progress. Distinct from ``HousekeepingStatus``: a task can be CANCELLED
    while the room stays exactly as dirty as it was, and a room can be made CLEAN with no task at
    all. Branching, so it gets a transition table like the reservation's rather than
    ``TICKET_FLOW``'s index arithmetic."""

    OPEN = "OPEN"
    IN_PROGRESS = "IN_PROGRESS"
    DONE = "DONE"
    CANCELLED = "CANCELLED"


# An attendant who has started can still be pulled off the room, which cancels the WORK and leaves
# the room DIRTY — because it is. DONE and CANCELLED are terminal: a room needing more work gets a
# NEW task, so the board always shows what is outstanding rather than reopened history.
HOUSEKEEPING_TASK_FLOW: dict[HousekeepingTaskStatus, frozenset[HousekeepingTaskStatus]] = {
    HousekeepingTaskStatus.OPEN: frozenset(
        {HousekeepingTaskStatus.IN_PROGRESS, HousekeepingTaskStatus.CANCELLED}
    ),
    HousekeepingTaskStatus.IN_PROGRESS: frozenset(
        {HousekeepingTaskStatus.DONE, HousekeepingTaskStatus.CANCELLED}
    ),
    HousekeepingTaskStatus.DONE: frozenset(),
    HousekeepingTaskStatus.CANCELLED: frozenset(),
}


# --- The HOTEL booking (Phase 20.2) -------------------------------------------


class RoomReservationStatus(StrEnum):
    """Lifecycle of a ROOM reservation — the HOTEL booking, not the restaurant's table.

    Named in full, next to ``ReservationStatus`` (the TABLE booking's), because this module holds
    both and a reader must never have to guess which one a bare ``Reservation`` meant.

    - **TENTATIVE** — asked for, holding NOTHING. A property takes unconfirmed enquiries (a website
      booking with no deposit, a corporate hold), so unlike the restaurant — where passing the
      pacing gate IS the confirmation — this booking has a state before the counter is touched.
    - **CONFIRMED** — what confirming enters, and the moment the gate is passed.
    - **CHECKED_IN** — the guest is in a physical room (``room_id`` is set). Still holding: the
      nights are being consumed, not released.
    - **CHECKED_OUT** — terminal, bookkeeping only.
    - **NO_SHOW** — terminal, and it releases NOTHING: the opposite of the restaurant's rule, and
      deliberate. The room stood empty and unsellable all night, so nothing is left to resell, and
      the property's protection against that loss is ``overbooking_limit`` — the no-show buffer it
      sold into in advance. Releasing here would spend that buffer twice.
    - **CANCELLED** — called off, releasing whatever it held. Unlike a table, a room-night cancelled
      at any point before arrival is genuinely resellable.
    """

    TENTATIVE = "TENTATIVE"
    CONFIRMED = "CONFIRMED"
    CHECKED_IN = "CHECKED_IN"
    CHECKED_OUT = "CHECKED_OUT"
    NO_SHOW = "NO_SHOW"
    CANCELLED = "CANCELLED"


# The legal moves, one frozenset per state; an empty set is terminal. Branching, so it is written
# out like RESERVATION_FLOW next door — and written ONCE, so the service, the router and the docs
# cannot disagree. A CHECKED_IN booking cannot be cancelled: the guest is in the room, and the
# correction wanted then is on their folio (Task 5).
ROOM_RESERVATION_FLOW: dict[RoomReservationStatus, frozenset[RoomReservationStatus]] = {
    RoomReservationStatus.TENTATIVE: frozenset(
        {RoomReservationStatus.CONFIRMED, RoomReservationStatus.CANCELLED}
    ),
    RoomReservationStatus.CONFIRMED: frozenset(
        {
            RoomReservationStatus.CHECKED_IN,
            RoomReservationStatus.NO_SHOW,
            RoomReservationStatus.CANCELLED,
        }
    ),
    RoomReservationStatus.CHECKED_IN: frozenset({RoomReservationStatus.CHECKED_OUT}),
    RoomReservationStatus.CHECKED_OUT: frozenset(),
    RoomReservationStatus.NO_SHOW: frozenset(),
    RoomReservationStatus.CANCELLED: frozenset(),
}

# The states that HOLD room-nights on the allotment counter, so "does this booking still own its
# nights" is written once and cannot drift between confirm, cancel, no-show and the date change.
# TENTATIVE is absent because it never took them; NO_SHOW and CHECKED_OUT because they spent them.
# CHECKED_IN is a domain fact no reader can OBSERVE yet, said here rather than left to be found:
# `_holds_allotment` is consulted only by cancel and the date change, and both refuse a CHECKED_IN
# booking before they ask. It stays because the set answers "which states own their nights" — a
# guest in the room plainly does — and PLAN 20.5's early departure is the reader that will see it.
ROOM_RESERVATION_HOLDS_ALLOTMENT: frozenset[RoomReservationStatus] = frozenset(
    {RoomReservationStatus.CONFIRMED, RoomReservationStatus.CHECKED_IN}
)

# What a room type's allotment row is born with when no manager has set one: no buffer at all.
# Overbooking is a deliberate revenue decision a property makes per room type per night, and a
# non-zero default would sell rooms nobody chose to oversell.
DEFAULT_OVERBOOKING_LIMIT = 0
