"""THE GATE ON THE GATE: every path that writes room supply locks the row that decides its delta.

Three review rounds of PLAN 20.2 found the same defect three times, one call site further over each
time — a function computing an allotment delta from state it had read WITHOUT a row lock, so two
concurrent requests both computed it and both applied it. A `-m pg` race pins each path that exists
today; this file is what catches the path that does not exist yet, because "the reviewer noticed"
is not a control and the next writer of this counter will not have read the other three.

It is a STATIC gate, in the shape of ``test_tenancy_grep_gate`` (the D-007 precedent) but over the
AST rather than a regex, and it asserts two things:

1. **The census is closed.** The set of functions that call ``allotment.adjust_allotment`` /
   ``adjust_sellable`` / ``apply_allotment_deltas`` is exactly :data:`SUPPLY_WRITERS`. A new writer
   fails here until somebody names it and its deciding row — which is also what keeps the paths ×
   locks table in ``docs/modules/hospitality.md`` and the PR body from outrunning the code.
2. **Each of them takes its lock first.** The declared getter is called with ``for_update=True`` on
   a line ABOVE the allotment call. Line order matters: a lock taken after the counter has been read
   serializes nothing.

What this canNOT see is a lock taken through some spelling it does not know, so the census in (1) is
the part that must stay honest — a writer added without an entry fails, and an entry cannot be added
without naming the row and the getter. The runtime proof that each lock is the RIGHT lock is the
`-m pg` race per path in ``test_room_booking_races.py``; this is the proof that no path is missing
one at all.
"""

import ast
from pathlib import Path

import pytest

_SERVICE = Path(__file__).resolve().parents[3] / "app" / "modules" / "hospitality" / "service"

# The three entry points that move `hsp_room_type_inventory`. `apply_allotment_deltas` is the
# private shape `adjust_allotment` delegates to and is listed so a caller cannot reach the counter
# by skipping the public helper.
_ALLOTMENT_WRITES = frozenset(
    {"adjust_allotment", "adjust_sellable", "apply_allotment_deltas"}
)

# EVERY path in the module that writes `rooms_sold` or `rooms_sellable`, and the row whose state
# decides its delta. `(file, function) -> (getter, what it locks)`.
#
# `rooms_sold` is decided by the RoomReservation being moved: the transition it is allowed to make
# is read off `ROOM_RESERVATION_FLOW` in Python, so two requests moving one booking both pass it
# unless the row is locked (a double-clicked Confirm).
#
# `rooms_sellable` is decided by the Room being changed: the type it is moving OUT of and the
# housekeeping status it is moving out of are both read off the row, so two requests moving one room
# both compute the same move unless the row is locked.
#
# The room TYPE row is locked by `allotment` itself, on both paths, and so is deliberately absent
# here — a caller cannot forget a lock the callee takes.
SUPPLY_WRITERS: dict[tuple[str, str], tuple[str, str]] = {
    ("room_reservations.py", "confirm_room_reservation"): ("get_room_reservation", "the booking"),
    ("room_reservations.py", "cancel_room_reservation"): ("get_room_reservation", "the booking"),
    ("room_reservations.py", "amend_room_reservation"): ("get_room_reservation", "the booking"),
    ("rooms.py", "update_room"): ("get_room", "the room"),
    ("rooms.py", "set_housekeeping_status"): ("get_room", "the room"),
}


def _called_name(node: ast.Call) -> str:
    """The bare function name of a call, whether written ``f()`` or ``module.f()``."""
    func = node.func
    if isinstance(func, ast.Attribute):
        return func.attr
    if isinstance(func, ast.Name):
        return func.id
    return ""


def _functions(path: Path) -> list[ast.AsyncFunctionDef | ast.FunctionDef]:
    tree = ast.parse(path.read_text(encoding="utf-8"))
    return [
        node
        for node in ast.walk(tree)
        if isinstance(node, ast.AsyncFunctionDef | ast.FunctionDef)
    ]


def _writers() -> dict[tuple[str, str], ast.AsyncFunctionDef | ast.FunctionDef]:
    """Every function under ``service/`` that calls into the allotment counter, keyed by
    ``(file, function)``. ``allotment.py`` itself is skipped: it IS the counter."""
    found: dict[tuple[str, str], ast.AsyncFunctionDef | ast.FunctionDef] = {}
    for path in sorted(_SERVICE.glob("*.py")):
        if path.name == "allotment.py":
            continue
        for function in _functions(path):
            calls = [node for node in ast.walk(function) if isinstance(node, ast.Call)]
            if any(_called_name(call) in _ALLOTMENT_WRITES for call in calls):
                found[(path.name, function.name)] = function
    return found


def test_the_census_of_allotment_writers_is_closed() -> None:
    """A new path into the counter fails until it is named here with the row it locks.

    This is the half that catches the defect the review found three times: each round fixed the
    call sites it was given, and the next round found another one. A census that fails on an
    UNKNOWN writer cannot be one call site behind.
    """
    found = set(_writers())
    declared = set(SUPPLY_WRITERS)
    assert found == declared, (
        "the set of functions writing rooms_sold/rooms_sellable has changed.\n"
        f"  undeclared (name it in SUPPLY_WRITERS with the row it locks): "
        f"{sorted(found - declared)}\n"
        f"  declared but gone (delete the entry): {sorted(declared - found)}"
    )


@pytest.mark.parametrize(("where", "getter"), sorted(SUPPLY_WRITERS.items()))
def test_every_allotment_writer_locks_the_row_that_decides_its_delta(
    where: tuple[str, str], getter: tuple[str, str]
) -> None:
    """The declared getter is called with ``for_update=True``, ABOVE the counter call.

    Mutation: drop the ``for_update=True`` from either ``rooms.update_room`` or
    ``rooms.set_housekeeping_status`` (the two this repair adds) and the matching case goes red;
    move the lock below the ``adjust_*`` call and it goes red on the ordering clause.
    """
    function = _writers()[where]
    getter_name, subject = getter
    calls = [node for node in ast.walk(function) if isinstance(node, ast.Call)]

    locked_at = [
        call.lineno
        for call in calls
        if _called_name(call) == getter_name
        and any(
            keyword.arg == "for_update" and keyword.value.value is True
            for keyword in call.keywords
            if isinstance(keyword.value, ast.Constant)
        )
    ]
    assert locked_at, (
        f"{where[0]}:{function.name} moves the allotment counter but never calls "
        f"{getter_name}(..., for_update=True) — {subject} is what decides its delta, and two "
        "concurrent requests reading it unlocked both compute the same delta and both apply it"
    )

    wrote_at = [call.lineno for call in calls if _called_name(call) in _ALLOTMENT_WRITES]
    assert min(locked_at) < min(wrote_at), (
        f"{where[0]}:{function.name} locks {subject} at line {min(locked_at)} but touches the "
        f"counter at line {min(wrote_at)} — a lock taken after the delta was computed serializes "
        "nothing"
    )
